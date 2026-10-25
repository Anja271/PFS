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
    def test_source_workflow_uses_vlast_only_for_channel_supplied_english(self) -> None:
        korean_only = {
            "subtitles": {
                "ko": [{"ext": "json3", "url": "https://example.test/ko"}],
            },
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "https://example.test/auto-en"}],
            },
        }
        self.assertTrue(MODULE.has_korean_captions(korean_only))
        self.assertFalse(MODULE.has_channel_english_captions(korean_only))
        self.assertEqual(MODULE.suggested_source_workflow(korean_only, True), "korean-only")

        assisted = {
            **korean_only,
            "subtitles": {
                **korean_only["subtitles"],
                "en-vlast": [{"ext": "json3", "url": "https://example.test/vlast-en"}],
            },
        }
        self.assertTrue(MODULE.has_channel_english_captions(assisted))
        self.assertEqual(MODULE.suggested_source_workflow(assisted, True), "vlast-assisted")

        self.assertEqual(
            MODULE.suggested_source_workflow({}, False, "full"),
            "existing-full-subtitles",
        )

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

    def test_fresh_priority_preview_reorders_without_dropping_videos(self) -> None:
        videos = [
            {"youtubeId": "newest1", "title": "Newest", "publishedAt": ""},
            {"youtubeId": "middle2", "title": "Middle", "publishedAt": ""},
            {"youtubeId": "archive3", "title": "Archive", "publishedAt": ""},
        ]
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        preview = {
            "generatedAt": "2026-10-24T00:00:00Z",
            "modifiesLiveQueue": False,
            "entries": [{"youtubeId": "archive3"}, {"youtubeId": "newest1"}],
        }
        ordered, active = MODULE.apply_recent_priority_preview(videos, preview, now)
        self.assertTrue(active)
        self.assertEqual(
            [video["youtubeId"] for video in ordered],
            ["archive3", "newest1", "middle2"],
        )

    def test_stale_priority_preview_falls_back_to_newest_first(self) -> None:
        videos = [
            {"youtubeId": "newest1", "title": "Newest", "publishedAt": ""},
            {"youtubeId": "archive3", "title": "Archive", "publishedAt": ""},
        ]
        preview = {
            "generatedAt": "2026-07-21T00:00:00Z",
            "modifiesLiveQueue": False,
            "entries": [{"youtubeId": "archive3"}],
        }
        ordered, active = MODULE.apply_recent_priority_preview(
            videos, preview, datetime(2026, 10, 25, tzinfo=timezone.utc)
        )
        self.assertFalse(active)
        self.assertEqual(ordered, videos)

    def test_retry_window_and_terminal_states(self) -> None:
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        recent = {"status": "no_heatmap", "checkedAt": "2026-07-19T00:00:00Z"}
        old = {"status": "no_heatmap", "checkedAt": "2026-06-01T00:00:00Z"}
        self.assertFalse(MODULE.should_scan(recent, now, timedelta(days=30), False))
        self.assertTrue(MODULE.should_scan(old, now, timedelta(days=30), False))
        self.assertFalse(MODULE.should_scan({"status": "ready"}, now, timedelta(days=30), False))
        self.assertTrue(MODULE.should_scan({"status": "ready"}, now, timedelta(days=30), True))

    def test_korean_only_candidate_remains_ready_without_vlast(self) -> None:
        video = {"youtubeId": "abc123XYZ", "title": "Older stream", "publishedAt": "2023-01-01"}
        info = {
            "title": "Older stream",
            "subtitles": {
                "ko": [{"ext": "json3", "url": "https://example.test/ko"}],
            },
            "heatmap": [{"start_time": 0, "end_time": 10, "value": 0.8}],
        }
        result = MODULE.classify(video, info, "2026-10-25T00:00:00Z")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["suggestedSourceWorkflow"], "korean-only")

    def test_existing_full_subtitles_make_heatmap_candidate_ready(self) -> None:
        video = {"youtubeId": "abc123XYZ", "title": "Translated stream", "publishedAt": "2026-10-01"}
        info = {
            "title": "Translated stream",
            "heatmap": [{"start_time": 0, "end_time": 10, "value": 0.8}],
        }
        original = MODULE.subtitle_coverage
        MODULE.subtitle_coverage = lambda _video_id: "full"
        try:
            result = MODULE.classify(video, info, "2026-10-25T00:00:00Z")
        finally:
            MODULE.subtitle_coverage = original
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["subtitleCoverage"], "full")
        self.assertEqual(result["suggestedSourceWorkflow"], "existing-full-subtitles")


if __name__ == "__main__":
    unittest.main()
