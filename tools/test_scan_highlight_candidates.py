#!/usr/bin/env python3
"""Small dependency-free checks for the highlight batch scanner."""

from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_highlight_candidates.py"
SPEC = importlib.util.spec_from_file_location("scan_highlight_candidates", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScannerTests(unittest.TestCase):
    def test_normalizes_and_groups_hot_points(self) -> None:
        points = MODULE.normalize_heatmap(
            [
                {"start_time": 0, "end_time": 10, "value": 0.2},
                {"start_time": 10, "end_time": 20, "value": 0.6},
                {"start_time": 20, "end_time": 30, "value": 1.0},
                {"start_time": 30, "end_time": 40, "value": 0.1},
                {"start_time": 40, "end_time": 50, "value": 0.7},
            ]
        )
        self.assertIsNotNone(points)
        self.assertEqual(
            MODULE.hot_clusters(points),
            [
                {"startSeconds": 10, "endSeconds": 30, "peakSeconds": 25, "peakValue": 1.0},
                {"startSeconds": 40, "endSeconds": 50, "peakSeconds": 45, "peakValue": 0.7},
            ],
        )

    def test_rejects_invalid_heatmap_order(self) -> None:
        self.assertIsNone(
            MODULE.normalize_heatmap(
                [
                    {"start_time": 10, "end_time": 20, "value": 0.5},
                    {"start_time": 10, "end_time": 30, "value": 0.6},
                ]
            )
        )

    def test_retry_window_and_terminal_states(self) -> None:
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        recent = {"status": "no_heatmap", "checkedAt": "2026-07-19T00:00:00Z"}
        old = {"status": "no_heatmap", "checkedAt": "2026-06-01T00:00:00Z"}
        self.assertFalse(MODULE.should_scan(recent, now, timedelta(days=30), False))
        self.assertTrue(MODULE.should_scan(old, now, timedelta(days=30), False))
        self.assertFalse(MODULE.should_scan({"status": "ready"}, now, timedelta(days=30), False))
        self.assertTrue(MODULE.should_scan({"status": "ready"}, now, timedelta(days=30), True))


if __name__ == "__main__":
    unittest.main()
