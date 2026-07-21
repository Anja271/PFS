#!/usr/bin/env python3
"""Dependency-light structural checks for the two-gate subtitle workflow."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_preparer():
    path = ROOT / "scripts" / "prepare_stream.py"
    spec = importlib.util.spec_from_file_location("prepare_stream", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load prepare_stream.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    for relative in (
        "scripts/prepare_stream.py",
        "scripts/finalize_subtitle_job.py",
        "scripts/publish_subtitle_job.py",
    ):
        ast.parse((ROOT / relative).read_text(encoding="utf-8"))

    preparer = load_preparer()
    cues = preparer.source_cues(
        {
            "events": [
                {"tStartMs": 1001, "segs": [{"utf8": "첫째"}]},
                {"tStartMs": 1900, "segs": [{"utf8": "둘째"}]},
                {"tStartMs": 4100, "segs": [{"utf8": "셋째"}]},
            ]
        }
    )
    assert [cue["startSeconds"] for cue in cues] == [1, 4]
    assert cues[0]["sourceParts"] == ["첫째", "둘째"]

    points = [
        {"startSeconds": 100.0, "endSeconds": 110.0, "value": 0.8},
        {"startSeconds": 120.0, "endSeconds": 130.0, "value": 0.7},
        {"startSeconds": 900.0, "endSeconds": 910.0, "value": 0.9},
    ]
    source = [
        {"startSeconds": second}
        for second in range(0, 1101)
    ]
    plan = preparer.scene_plan(points, source)
    assert len(plan) == 2
    assert all(scene["parallelEligible"] is False for scene in plan)
    assert all(scene["independenceStatus"] == "requires-context-review" for scene in plan)
    publish_source = (ROOT / "scripts" / "publish_subtitle_job.py").read_text(encoding="utf-8")
    assert "merge_prepared_heatmap(work, args.video_id)" in publish_source
    assert '"data/heatmaps.json"' in publish_source
    print("PASS: two-gate scripts parse; cue merging and conservative scene planning work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
