#!/usr/bin/env python3
"""Checks for sealing highlight selections that reuse a full subtitle file."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "finalize_existing_subtitle_highlights.py"
SPEC = importlib.util.spec_from_file_location("finalize_existing_subtitle_highlights_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExistingSubtitleHighlightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cues = [(10.0, 14.999), (15.0, 19.999), (30.0, 39.999)]
        self.clusters = [
            {"peakSeconds": 12, "startSeconds": 5, "endSeconds": 20},
            {"peakSeconds": 35, "startSeconds": 30, "endSeconds": 40},
        ]

    def test_connected_peaks_can_share_one_reviewed_scene(self) -> None:
        scenes = MODULE.validate_scenes(
            [{"startSeconds": 10, "endSeconds": 40, "title": "One complete conversation"}],
            self.cues,
            self.clusters,
        )
        self.assertEqual(len(scenes), 1)

    def test_every_preserved_peak_must_be_covered(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "do not preserve"):
            MODULE.validate_scenes(
                [{"startSeconds": 10, "endSeconds": 20, "title": "Only the first peak"}],
                self.cues,
                self.clusters,
            )

    def test_scene_must_start_on_existing_vtt_cue(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "begin on an existing VTT cue"):
            MODULE.validate_scenes(
                [{"startSeconds": 11, "endSeconds": 40, "title": "Bad start"}],
                self.cues,
                self.clusters,
            )


if __name__ == "__main__":
    unittest.main()
