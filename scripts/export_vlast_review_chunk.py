#!/usr/bin/env python3
"""Print one prepared Korean/English caption span for sequential review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stamp(milliseconds: int) -> str:
    seconds = milliseconds // 1000
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    parser.add_argument("start_seconds", type=int)
    parser.add_argument("end_seconds", type=int)
    args = parser.parse_args()
    work = ROOT / ".subtitle-work" / args.video_id / "vlast-assisted"
    metadata = json.loads((work / "pilot-metadata.json").read_text(encoding="utf-8"))
    temporary = Path(metadata["temporarySourceDirectory"])
    korean = json.loads((temporary / "korean-events.json").read_text(encoding="utf-8"))
    english = json.loads((temporary / "english-events.json").read_text(encoding="utf-8"))
    start_ms = args.start_seconds * 1000
    end_ms = args.end_seconds * 1000
    for index, event in enumerate(english):
        event_start = int(event["startMs"])
        if event_start < start_ms or event_start >= end_ms:
            continue
        next_start = (
            int(english[index + 1]["startMs"])
            if index + 1 < len(english)
            else event_start + int(event.get("durationMs") or 0)
        )
        sources = [
            str(item.get("text") or "")
            for item in korean
            if event_start <= int(item["startMs"]) < next_start
        ]
        print(f"\n[{stamp(event_start)} / {event_start}]")
        for source in sources:
            print(f"KO {source}")
        print(f"EN {event['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
