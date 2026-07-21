#!/usr/bin/env python3
"""Small dependency-free checks for the priority-preview ranking rules."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_stream_priority_preview.py"
PREVIEW_PATH = ROOT / "data" / "stream-priority-preview.json"


def main() -> int:
    ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    preview = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    entries = preview["entries"]

    assert preview["modifiesLiveQueue"] is False
    assert preview["source"] == "https://www.youtube.com/@plave_official/streams"
    assert preview["method"]["scoreWeights"]["longTermViewVelocity"] == 0
    assert len(entries) == preview["eligibleUntranslatedStreams"]
    assert len({entry["youtubeId"] for entry in entries}) == len(entries)
    assert [entry["previewRank"] for entry in entries] == list(
        range(1, len(entries) + 1)
    )

    first_six_lanes = [entry["selectionLane"] for entry in entries[:6]]
    assert first_six_lanes == [
        "priority",
        "priority",
        "recent",
        "priority",
        "archive",
        "recent",
    ]
    assert all(entry["playlistIndex"] < 24 for entry in entries[:30] if entry["selectionLane"] == "recent")

    print(f"Priority preview validation passed for {len(entries)} streams.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
