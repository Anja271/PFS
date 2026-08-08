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
STANDALONE_JA_RE = re.compile(r"(?<![가-힣])자(?![가-힣])")
ROMANIZED_JA_RE = re.compile(r"\bja\b", re.IGNORECASE)
DUDU_VERB_RE = re.compile(r"(?:(?:두두|두도)(?:하|해|한|할|합)|두(?:하|한다|할|합))")
DUDU_ENGLISH_RE = re.compile(r"\bdudu(?:handa|-ing)?\b", re.IGNORECASE)
BONG_CATCHPHRASE_RE = re.compile(r"(?:봉국|봉극|벙커스|벙크스|벙크|봉끝)")
BONG_CATCHPHRASE_ENGLISH_RE = re.compile(r"\bBong(?:uk|us|-kkeut)\b", re.IGNORECASE)
HAMIN_PUN_RE = re.compile(r"(?:그만하민|그만민|마민|마인|넘어가민|넘어가미)")
SPLIT_GEUMAN_HAMIN_RE = re.compile(r"그만\s+하면")
HAMIN_PUN_ENGLISH_RE = re.compile(r"\b(?:[A-Za-z]+-)+(?:Hamin|min)\b", re.IGNORECASE)
SHORT_CUE_MILLISECONDS = 1250
MEDIUM_CUE_MILLISECONDS = 2250
SHORT_CUE_CHARACTER_LIMIT = 42
MEDIUM_CUE_CHARACTER_LIMIT = 58


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


def readability_warnings(cues: list[dict[str, object]]) -> list[str]:
    """Return non-blocking warnings for unusually dense short cues.

    Rapid chants, deliberate repetitions, and sound descriptions sometimes
    justify dense timing, so these warnings require editorial review rather
    than failing an otherwise valid package automatically.
    """

    warnings: list[str] = []
    for number, cue in enumerate(cues, start=1):
        duration = int(cue["end"]) - int(cue["start"]) + 1
        characters = len(re.sub(r"\s+", " ", str(cue["text"])).strip())
        limit = None
        if duration <= SHORT_CUE_MILLISECONDS:
            limit = SHORT_CUE_CHARACTER_LIMIT
        elif duration <= MEDIUM_CUE_MILLISECONDS:
            limit = MEDIUM_CUE_CHARACTER_LIMIT
        if limit is not None and characters > limit:
            warnings.append(
                f"cue {number}: {characters} characters in {duration / 1000:.3f}s "
                f"(review compression or confirm a justified rapid delivery)"
            )
    return warnings


def print_readability_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    for warning in warnings[:10]:
        print(f"WARNING: readability: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: readability: {len(warnings) - 10} additional dense cue(s)")


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
        lowered = text.lower()
        if not any(
            marker in lowered
            for marker in ("[music]", "singing", " sing", "sings", "perform", "listen")
        ):
            raise ValueError(f"cue {index}: source music marker lacks an approved description")


def validate_standalone_ja(cues: list[dict[str, object]], source: list[dict[str, object]]) -> None:
    """Preserve Bamby's MC `자` sound and the members' imitations cue by cue."""

    for index, (translated, original) in enumerate(zip(cues, source), start=1):
        expected = len(STANDALONE_JA_RE.findall(str(original.get("source", ""))))
        actual = len(ROMANIZED_JA_RE.findall(str(translated["text"])))
        if actual != expected:
            raise ValueError(
                f"cue {index}: standalone 자/ja count differs "
                f"(source={expected}, English={actual})"
            )


def validate_duduhanda(cues: list[dict[str, object]], source: list[dict[str, object]]) -> None:
    """Prevent Yejun's coined catch-all verb from being flattened away."""

    for index, (translated, original) in enumerate(zip(cues, source), start=1):
        if not DUDU_VERB_RE.search(str(original.get("source", ""))):
            continue
        if not DUDU_ENGLISH_RE.search(str(translated["text"])):
            raise ValueError(f"cue {index}: verbal duduhanda form was not preserved in English")


def validate_bong_catchphrase(cues: list[dict[str, object]], source: list[dict[str, object]]) -> None:
    """Keep Bamby/Bonggu's coined Bong-forms visible across later callbacks."""

    for index, (translated, original) in enumerate(zip(cues, source), start=1):
        if not BONG_CATCHPHRASE_RE.search(str(original.get("source", ""))):
            continue
        if not BONG_CATCHPHRASE_ENGLISH_RE.search(str(translated["text"])):
            raise ValueError(f"cue {index}: Bonguk/Bongus catchphrase reference was lost")


def validate_hamin_wordplay(cues: list[dict[str, object]], source: list[dict[str, object]]) -> None:
    """Keep intentional -Hamin/-min verbs, including a split-ASR first coinage."""

    sources = [str(original.get("source", "")) for original in source]
    for index, (translated, original) in enumerate(zip(cues, source), start=1):
        source_text = str(original.get("source", ""))
        explicit_wordplay = bool(HAMIN_PUN_RE.search(source_text))
        split_first_coinage = bool(SPLIT_GEUMAN_HAMIN_RE.search(source_text)) and any(
            "그만하민" in following for following in sources[index : index + 8]
        )
        if not explicit_wordplay and not split_first_coinage:
            continue
        if not HAMIN_PUN_ENGLISH_RE.search(str(translated["text"])):
            raise ValueError(f"cue {index}: -Hamin/-min wordplay was not preserved in English")


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
        validate_standalone_ja(cues, source)
        validate_duduhanda(cues, source)
        validate_bong_catchphrase(cues, source)
        validate_hamin_wordplay(cues, source)
        chapters = validate_chapters(args.chapters, cues)
        warnings = readability_warnings(cues)
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print_readability_warnings(warnings)
    print(
        "PASS: "
        f"{len(cues)} cues, complete source coverage, strict timing, no overlaps, "
        f"UTF-8, line-count/terminology/song/ja/duduhanda/Bong/Hamin checks, and {len(chapters)} valid chapters."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
