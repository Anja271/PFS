#!/usr/bin/env python3
"""Validate one PLAVE subtitle candidate and its chapter navigation file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TIMING_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})$"
)
HTML_RE = re.compile(r"<[^>]+>")
FORBIDDEN_RE = re.compile(
    r"\b(?:bro|brother|Bambi|Banbi|Flea|Playa|Ha-min|Eun-ho|Ye-jun)\b|\bMr\.",
    re.IGNORECASE,
)
MALFORMED_HYUNG_RE = re.compile(r"\b(?:hung|hyoung|hyong|Junhyung|Ye-hyung)\b", re.IGNORECASE)


def milliseconds(groups: tuple[str, ...]) -> int:
    hours, minutes, seconds, millis = map(int, groups)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("minute or second component is out of range")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def load_utf8(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"{path}: not readable valid UTF-8 ({error})") from error


def parse_vtt(path: Path) -> list[dict[str, object]]:
    text = load_utf8(path)
    if not text.startswith("WEBVTT\n\n"):
        raise ValueError("VTT must begin with WEBVTT followed by a blank line")
    blocks = text.rstrip("\n").split("\n\n")[1:]
    cues: list[dict[str, object]] = []
    for number, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 2:
            raise ValueError(f"cue {number}: missing subtitle text")
        match = TIMING_RE.fullmatch(lines[0])
        if not match:
            raise ValueError(f"cue {number}: invalid timing line {lines[0]!r}")
        start = milliseconds(match.groups()[:4])
        end = milliseconds(match.groups()[4:])
        text_lines = lines[1:]
        if not 1 <= len(text_lines) <= 2 or any(not line.strip() for line in text_lines):
            raise ValueError(f"cue {number}: subtitle text must use one or two non-empty lines")
        subtitle = "\n".join(text_lines)
        if HTML_RE.search(subtitle):
            raise ValueError(f"cue {number}: HTML is not allowed")
        if FORBIDDEN_RE.search(subtitle) or MALFORMED_HYUNG_RE.search(subtitle):
            raise ValueError(f"cue {number}: forbidden terminology in {subtitle!r}")
        if "♪" in subtitle:
            raise ValueError(f"cue {number}: music-note caption survived the song review")
        if end <= start:
            raise ValueError(f"cue {number}: end time is not after start time")
        cues.append({"start": start, "end": end, "text": subtitle})
    return cues


def validate_timing(cues: list[dict[str, object]], source: list[dict[str, object]]) -> None:
    source_starts = [int(cue["startSeconds"]) * 1000 for cue in source]
    if source_starts != sorted(set(source_starts)):
        raise ValueError("structured source starts are not strictly increasing and unique")
    starts = [int(cue["start"]) for cue in cues]
    if starts != source_starts:
        missing = sorted(set(source_starts) - set(starts))
        extra = sorted(set(starts) - set(source_starts))
        raise ValueError(f"timestamp coverage differs (missing={missing[:5]}, extra={extra[:5]})")
    for index, cue in enumerate(cues[:-1]):
        following = cues[index + 1]
        if int(cue["end"]) != int(following["start"]) - 1:
            raise ValueError(f"cue {index + 1}: end is not next start minus 1 ms")
        if int(cue["end"]) >= int(following["start"]):
            raise ValueError(f"cue {index + 1}: overlaps the following cue")


def validate_source_music(cues: list[dict[str, object]], source: list[dict[str, object]]) -> None:
    for index, (translated, original) in enumerate(zip(cues, source), start=1):
        if "♪" not in str(original.get("source", "")):
            continue
        text = str(translated["text"])
        if not ("[Music]" in text or "performs" in text):
            raise ValueError(f"cue {index}: source music marker lacks an approved description")


def validate_chapters(path: Path, cues: list[dict[str, object]]) -> list[dict[str, object]]:
    try:
        chapters = json.loads(load_utf8(path))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid chapter JSON ({error})") from error
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("chapter JSON must be a non-empty list")
    cue_seconds = {int(cue["start"]) // 1000 for cue in cues}
    previous = -1
    for number, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict) or set(chapter) != {"startSeconds", "title"}:
            raise ValueError(f"chapter {number}: use exactly startSeconds and title")
        start = chapter["startSeconds"]
        title = chapter["title"]
        if isinstance(start, bool) or not isinstance(start, int) or start <= previous:
            raise ValueError(f"chapter {number}: startSeconds is invalid or non-increasing")
        if start not in cue_seconds:
            raise ValueError(f"chapter {number}: startSeconds does not match a VTT cue")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise ValueError(f"chapter {number}: title is invalid")
        if "♪" in title or HTML_RE.search(title):
            raise ValueError(f"chapter {number}: title contains forbidden markup or lyric notation")
        previous = start
    if chapters[0]["startSeconds"] != min(cue_seconds):
        raise ValueError("the first chapter must match the first VTT cue")
    return chapters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--vtt", required=True, type=Path)
    parser.add_argument("--chapters", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = json.loads(load_utf8(args.source))
        if not isinstance(source, list) or not source:
            raise ValueError("structured source must be a non-empty JSON list")
        cues = parse_vtt(args.vtt)
        validate_timing(cues, source)
        validate_source_music(cues, source)
        chapters = validate_chapters(args.chapters, cues)
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: "
        f"{len(cues)} cues, complete source coverage, strict timing, no overlaps, "
        f"UTF-8, line-count/terminology/song checks, and {len(chapters)} valid chapters."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
