#!/usr/bin/env python3
"""Regression checks for append-only curated highlight publication."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_highlights.py"
SPEC = importlib.util.spec_from_file_location("update_highlights_archive_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LegendaryArchiveTests(unittest.TestCase):
    def test_missing_or_cold_heatmap_never_removes_a_scene(self) -> None:
        scene = {
            "startSeconds": 100,
            "endSeconds": 200,
            "title": "Kept forever",
            "legendary": False,
            "everMostReplayed": True,
        }
        self.assertEqual(
            MODULE.annotate_curated_scenes([scene], None),
            [{**scene, "currentlyMostReplayed": False}],
        )
        cold = [{"startSeconds": 110.0, "endSeconds": 120.0, "value": 0.2}]
        annotated = MODULE.annotate_curated_scenes([scene], cold)
        self.assertEqual(len(annotated), 1)
        self.assertFalse(annotated[0]["currentlyMostReplayed"])

    def test_current_hot_status_is_annotation_not_admission(self) -> None:
        scene = {
            "startSeconds": 100,
            "endSeconds": 200,
            "title": "Still curated",
            "legendary": True,
            "everMostReplayed": True,
        }
        hot = [{"startSeconds": 110.0, "endSeconds": 120.0, "value": 0.8}]
        annotated = MODULE.annotate_curated_scenes([scene], hot)
        self.assertTrue(annotated[0]["currentlyMostReplayed"])
        self.assertEqual(annotated[0]["peakSeconds"], 115)

    def test_automatic_rebuild_cannot_remove_a_published_scene(self) -> None:
        previous = [
            {
                "youtubeId": "abc123XYZ",
                "scenes": [{"startSeconds": 100, "endSeconds": 200, "title": "Published"}],
            }
        ]
        with self.assertRaisesRegex(RuntimeError, "refusing to remove"):
            MODULE.require_append_only_archive(previous, [])
        MODULE.require_append_only_archive(previous, previous)

    def test_historical_heatmap_evidence_cannot_be_removed(self) -> None:
        previous = [{
            "youtubeId": "abc123XYZ",
            "scenes": [{
                "startSeconds": 100,
                "endSeconds": 200,
                "title": "Once hot",
                "legendary": False,
                "everMostReplayed": True,
            }],
        }]
        current = [{
            "youtubeId": "abc123XYZ",
            "scenes": [{
                "startSeconds": 100,
                "endSeconds": 200,
                "title": "Once hot",
                "legendary": False,
                "everMostReplayed": False,
            }],
        }]
        with self.assertRaisesRegex(RuntimeError, "everMostReplayed"):
            MODULE.require_append_only_archive(previous, current)

    def test_every_generated_scene_has_a_curated_source_record(self) -> None:
        manifest = json.loads((ROOT / "data" / "highlights.json").read_text(encoding="utf-8"))
        generated = {
            (stream["youtubeId"], scene["startSeconds"], scene["endSeconds"])
            for stream in manifest
            for scene in stream["scenes"]
        }
        curated = set()
        for path in (ROOT / "highlights").glob("*.json"):
            for scene in json.loads(path.read_text(encoding="utf-8")):
                curated.add((path.stem, scene["startSeconds"], scene["endSeconds"]))
        self.assertEqual(generated, curated)
        self.assertGreaterEqual(len(generated), 24)
        for stream in manifest:
            for scene in stream["scenes"]:
                self.assertIsInstance(scene.get("legendary"), bool)
                self.assertIsInstance(scene.get("everMostReplayed"), bool)
                self.assertTrue(scene["legendary"] or scene["everMostReplayed"])


if __name__ == "__main__":
    unittest.main()
