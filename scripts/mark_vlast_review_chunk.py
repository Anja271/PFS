#!/usr/bin/env python3
"""Record a completed two-pass context review in the single progress ledger."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    parser.add_argument("start_seconds", type=int)
    parser.add_argument("end_seconds", type=int)
    parser.add_argument("--corrections", type=int, required=True)
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")
    if args.start_seconds < 0 or args.end_seconds <= args.start_seconds:
        raise RuntimeError("invalid review range")
    work = WORK_ROOT / args.video_id / "vlast-assisted"
    progress_path = work / "translation-progress.json"
    progress = read_json(progress_path)
    metadata = read_json(work / "pilot-metadata.json")
    if args.end_seconds > int(metadata["durationSeconds"]):
        raise RuntimeError("review range exceeds video duration")
    start_ms = args.start_seconds * 1000
    end_ms = args.end_seconds * 1000
    ranges = progress.get("reviewedContextRanges") or []
    if not isinstance(ranges, list):
        raise RuntimeError("reviewedContextRanges must be a list")
    ranges = [
        item
        for item in ranges
        if not (int(item["startMs"]) == start_ms and int(item["endMs"]) == end_ms)
    ]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ranges.append(
        {
            "startMs": start_ms,
            "endMs": end_ms,
            "status": "reviewed",
            "reviewPasses": 2,
            "correctionCount": args.corrections,
            "note": args.note,
            "reviewedAt": now,
        }
    )
    progress["reviewedContextRanges"] = sorted(ranges, key=lambda item: int(item["startMs"]))
    progress["updatedAt"] = now
    atomic_write_json(progress_path, progress)
    print(
        f"Marked {args.video_id} {args.start_seconds}-{args.end_seconds}s as reviewed in two passes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
