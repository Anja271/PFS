#!/usr/bin/env python3
"""Validate the local, non-publishable VLAST-assisted subtitle pilot."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
TIMING_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})$"
)
HTML_RE = re.compile(r"<[^>]+>")
FORBIDDEN_RE = re.compile(r"\b(?:bro|brother|big brother|Mr\.)\b", re.IGNORECASE)
MALFORMED_HYUNG_RE = re.compile(
    r"\b(?:YEJUN|NOAH|BAMBY|EUNHO|HAMIN)(?:\s+hyung|-?Hyung|hyung)\b"
)


def milliseconds(values: tuple[str, str, str, str]) -> int:
    hours, minutes, seconds, millis = map(int, values)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("invalid timestamp component")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def parse_vtt(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("WEBVTT\n\n"):
        raise ValueError("VTT must start with WEBVTT and a blank line")
    cues = []
    for number, block in enumerate(text.strip().split("\n\n")[1:], start=1):
        lines = block.splitlines()
        if len(lines) not in (2, 3):
            raise ValueError(f"cue {number}: expected one or two text lines")
        match = TIMING_RE.fullmatch(lines[0])
        if not match:
            raise ValueError(f"cue {number}: malformed timing")
        start = milliseconds(match.groups()[:4])
        end = milliseconds(match.groups()[4:])
        if end <= start:
            raise ValueError(f"cue {number}: non-positive duration")
        subtitle = "\n".join(lines[1:])
        if HTML_RE.search(subtitle):
            raise ValueError(f"cue {number}: HTML is not allowed")
        if FORBIDDEN_RE.search(subtitle):
            raise ValueError(f"cue {number}: forbidden relationship term")
        if MALFORMED_HYUNG_RE.search(subtitle):
            raise ValueError(f"cue {number}: malformed member-hyung form")
        cues.append({"start": start, "end": end, "text": subtitle})
    if not cues:
        raise ValueError("VTT contains no cues")
    for number, cue in enumerate(cues[1:], start=2):
        previous = cues[number - 2]
        if cue["start"] <= previous["start"]:
            raise ValueError(f"cue {number}: starts are not strictly increasing")
        if cue["start"] < previous["end"]:
            raise ValueError(f"cue {number}: overlaps the previous cue")
    return cues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")
    work = WORK_ROOT / args.video_id / "vlast-assisted"
    metadata = json.loads((work / "pilot-metadata.json").read_text(encoding="utf-8"))
    report = json.loads((work / "pilot-report.json").read_text(encoding="utf-8"))
    progress = json.loads((work / "translation-progress.json").read_text(encoding="utf-8"))
    overrides = json.loads((work / "editorial-overrides.json").read_text(encoding="utf-8"))
    audit = json.loads((work / "quality-audit.json").read_text(encoding="utf-8"))
    song_ranges = json.loads((work / "confirmed-song-ranges.json").read_text(encoding="utf-8"))
    cues = parse_vtt(work / "candidate.diagnostic.vtt")

    if metadata.get("youtubeId") != args.video_id or report.get("youtubeId") != args.video_id:
        raise RuntimeError("pilot files belong to another video")
    if metadata.get("mediaDownloaded") is not False:
        raise RuntimeError("metadata does not affirm that media was not downloaded")
    if report.get("status") != "diagnostic-pilot-not-publication-ready":
        raise RuntimeError("pilot must remain explicitly non-publication-ready")
    if report.get("pilotOverlapCount") != 0:
        raise RuntimeError("report records remaining overlaps")
    if report.get("pilotCueCount") != len(cues):
        raise RuntimeError("VTT cue count differs from report")
    if report.get("appliedKoreanLedEditorialOverrides") != len(overrides):
        raise RuntimeError("editorial override count differs from report")
    if progress.get("status") not in {"diagnostic-candidate-built", "full-context-review-queued", "review-complete"}:
        raise RuntimeError("progress has an invalid assisted-workflow status")
    if progress.get("reviewSamples") != overrides:
        raise RuntimeError("single progress file does not preserve the sample review ledger")
    if report.get("replacedLyricEvents", 0) <= 0 or not song_ranges:
        raise RuntimeError("confirmed song ranges were not replaced with descriptions")
    if report.get("restoredStandaloneJaMarkers", 0) <= 0:
        raise RuntimeError("Korean standalone ja markers were not restored")
    if args.require_reviewed:
        if progress.get("status") != "review-complete":
            raise RuntimeError("full contextual review is not complete")
        if audit.get("pendingIssueCount") != 0:
            raise RuntimeError("quality audit still contains pending issues")
        chunks = audit.get("reviewChunks")
        if not isinstance(chunks, list) or not chunks or any(
            chunk.get("status") != "reviewed" for chunk in chunks
        ):
            raise RuntimeError("not every context chunk has been reviewed")
    forbidden = list(work.glob("source*.json3")) + list(work.glob("*events.json"))
    if forbidden:
        raise RuntimeError("raw or normalized source caption bodies leaked into the repository work tree")
    if list(work.glob("*progress-[0-9]*.json")):
        raise RuntimeError("numbered progress artifacts are forbidden")
    print(
        f"PASS: {args.video_id} diagnostic pilot has {len(cues)} ordered, "
        f"non-overlapping cues, at most two lines, {len(overrides)} Korean-led "
        f"corrections, {audit.get('pendingIssueCount')} pending audit items, and no "
        "in-repository raw caption source files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
