#!/usr/bin/env python3
"""Validate a reviewed highlight-only VTT against the complete structured source."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from validate_subtitle_package import load_utf8, parse_vtt, validate_source_music


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--vtt", required=True, type=Path)
    parser.add_argument("--scenes", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = json.loads(load_utf8(args.source))
        scenes = json.loads(load_utf8(args.scenes))
        cues = parse_vtt(args.vtt)
        if not isinstance(source, list) or not source:
            raise ValueError("structured source must be a non-empty list")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("scenes must be a non-empty list")

        previous_end = -1
        for number, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict) or set(scene) != {"startSeconds", "endSeconds", "title"}:
                raise ValueError(f"scene {number}: use exactly startSeconds, endSeconds, and title")
            start, end, title = scene["startSeconds"], scene["endSeconds"], scene["title"]
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or start < previous_end
                or end <= start
            ):
                raise ValueError(f"scene {number}: invalid or overlapping boundaries")
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
                raise ValueError(f"scene {number}: invalid title")
            previous_end = end

        source_starts = [int(cue["startSeconds"]) for cue in source]
        if source_starts != sorted(set(source_starts)):
            raise ValueError("full source starts are not strictly increasing and unique")
        source_index = {start: index for index, start in enumerate(source_starts)}
        expected = [
            cue
            for cue in source
            if any(scene["startSeconds"] <= int(cue["startSeconds"]) < scene["endSeconds"] for scene in scenes)
        ]
        expected_starts = [int(cue["startSeconds"]) * 1000 for cue in expected]
        actual_starts = [int(cue["start"]) for cue in cues]
        if actual_starts != expected_starts:
            missing = sorted(set(expected_starts) - set(actual_starts))
            extra = sorted(set(actual_starts) - set(expected_starts))
            raise ValueError(f"partial timestamp coverage differs (missing={missing[:5]}, extra={extra[:5]})")

        for number, (translated, original) in enumerate(zip(cues, expected), start=1):
            start_seconds = int(original["startSeconds"])
            index = source_index[start_seconds]
            if index + 1 >= len(source_starts):
                raise ValueError(f"cue {number}: no following full-source timestamp")
            expected_end = source_starts[index + 1] * 1000 - 1
            if int(translated["end"]) != expected_end:
                raise ValueError(f"cue {number}: end is not the following full-source start minus 1 ms")
        validate_source_music(cues, expected)

        for number, scene in enumerate(scenes, start=1):
            contained = [start // 1000 for start in actual_starts if scene["startSeconds"] <= start // 1000 < scene["endSeconds"]]
            if not contained or contained[0] != scene["startSeconds"]:
                raise ValueError(f"scene {number}: first boundary does not match a VTT cue")
        if any(
            not any(scene["startSeconds"] <= start // 1000 < scene["endSeconds"] for scene in scenes)
            for start in actual_starts
        ):
            raise ValueError("a VTT cue lies outside the declared scenes")
    except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1

    print(
        "PASS: "
        f"{len(cues)} partial cues across {len(scenes)} scene(s), complete selected-source coverage, "
        "strict full-source timing, no overlaps, UTF-8, line-count/terminology/song checks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
