#!/usr/bin/env python3
"""Build static subtitle-coverage and Most replayed manifests."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VIDEOS_PATH = ROOT / "data" / "videos.json"
CHAPTERS_PATH = ROOT / "data" / "chapters.json"
HEATMAPS_PATH = ROOT / "data" / "heatmaps.json"
HIGHLIGHTS_PATH = ROOT / "data" / "highlights.json"
COVERAGE_PATH = ROOT / "data" / "subtitle-coverage.json"
SUBTITLES_DIR = ROOT / "subtitles"
PARTIAL_SUBTITLES_DIR = ROOT / "highlight-subtitles"
PARTIAL_SCENES_DIR = ROOT / "highlights"
METADATA_DIR = ROOT / "metadata"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMING_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})$"
)
HOT_THRESHOLD = 0.5


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return fallback


def parse_timestamp(groups: tuple[str, ...]) -> float:
    hours, minutes, seconds, millis = map(int, groups)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("VTT timestamp component is out of range")
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_vtt_ranges(path: Path) -> list[tuple[float, float]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RuntimeError(f"Cannot read {path.relative_to(ROOT)} as UTF-8: {error}") from error
    if not text.startswith("WEBVTT\n\n"):
        raise RuntimeError(f"{path.relative_to(ROOT)} must begin with WEBVTT and a blank line")

    ranges: list[tuple[float, float]] = []
    previous_start = -1.0
    previous_end = -1.0
    for line in text.splitlines():
        if "-->" not in line:
            continue
        match = TIMING_RE.fullmatch(line.strip())
        if not match:
            raise RuntimeError(f"Invalid timing line in {path.relative_to(ROOT)}: {line!r}")
        start = parse_timestamp(match.groups()[:4])
        end = parse_timestamp(match.groups()[4:])
        if start <= previous_start or start < previous_end or end <= start:
            raise RuntimeError(f"Invalid or overlapping cue order in {path.relative_to(ROOT)}")
        ranges.append((start, end))
        previous_start = start
        previous_end = end
    if not ranges:
        raise RuntimeError(f"{path.relative_to(ROOT)} has no valid cues")
    return ranges


def normalize_partial_scenes(video_id: str, raw: Any, cue_ranges: list[tuple[float, float]]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"highlights/{video_id}.json must be a non-empty list")
    scenes: list[dict[str, Any]] = []
    previous_end = -1
    for index, scene in enumerate(raw, start=1):
        if not isinstance(scene, dict) or set(scene) != {"startSeconds", "endSeconds", "title"}:
            raise RuntimeError(
                f"Scene {index} in highlights/{video_id}.json must use exactly "
                "startSeconds, endSeconds, and title"
            )
        start = scene["startSeconds"]
        end = scene["endSeconds"]
        title = scene["title"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or start < previous_end
        ):
            raise RuntimeError(f"Scene {index} in highlights/{video_id}.json has invalid boundaries")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise RuntimeError(f"Scene {index} in highlights/{video_id}.json has an invalid title")
        contained = [(cue_start, cue_end) for cue_start, cue_end in cue_ranges if start <= cue_start < end]
        if not contained or contained[0][0] != start:
            raise RuntimeError(
                f"Scene {index} in highlights/{video_id}.json must begin at the first matching VTT cue"
            )
        if any(cue_end > end for _, cue_end in contained):
            raise RuntimeError(f"A cue crosses scene {index}'s declared end in highlights/{video_id}.json")
        scenes.append({"startSeconds": start, "endSeconds": end, "title": title.strip()})
        previous_end = end
    if any(not any(scene["startSeconds"] <= start < scene["endSeconds"] for scene in scenes) for start, _ in cue_ranges):
        raise RuntimeError(f"highlight-subtitles/{video_id}.vtt contains cues outside declared scenes")
    return scenes


def load_metadata(video_id: str, video: dict[str, Any]) -> dict[str, str]:
    raw = load_json(METADATA_DIR / f"{video_id}.json", {})
    if not isinstance(raw, dict):
        raw = {}
    date = raw.get("date") if isinstance(raw.get("date"), str) else ""
    if date and not DATE_RE.fullmatch(date):
        raise RuntimeError(f"metadata/{video_id}.json has an invalid date")
    display_title = raw.get("displayTitle") if isinstance(raw.get("displayTitle"), str) else ""
    original_title = raw.get("originalTitle") if isinstance(raw.get("originalTitle"), str) else ""
    return {
        "date": date or str(video.get("publishedAt") or ""),
        "displayTitle": display_title.strip() or str(video.get("title") or "").strip(),
        "originalTitle": original_title.strip() or str(video.get("title") or "").strip(),
    }


def midpoint(point: dict[str, Any]) -> float:
    return float(point["startSeconds"]) + (float(point["endSeconds"]) - float(point["startSeconds"])) / 2


def hot_scenes_from_chapters(
    chapters: list[dict[str, Any]], heatmap: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not chapters or not heatmap:
        return []
    duration = math.ceil(max(float(point["endSeconds"]) for point in heatmap))
    scenes: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters):
        start = int(chapter["startSeconds"])
        end = int(chapters[index + 1]["startSeconds"]) if index + 1 < len(chapters) else duration
        matching = [point for point in heatmap if start <= midpoint(point) < end]
        if not matching:
            continue
        hottest = max(matching, key=lambda point: float(point["value"]))
        if float(hottest["value"]) < HOT_THRESHOLD:
            continue
        scenes.append(
            {
                "startSeconds": start,
                "endSeconds": end,
                "title": str(chapter["title"]).strip(),
                "peakSeconds": round(midpoint(hottest)),
                "peakValue": round(float(hottest["value"]), 6),
            }
        )
    return scenes


def hot_partial_scenes(
    scenes: list[dict[str, Any]], heatmap: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for scene in scenes:
        matching = [
            point
            for point in heatmap
            if scene["startSeconds"] <= midpoint(point) < scene["endSeconds"]
        ]
        if not matching:
            continue
        hottest = max(matching, key=lambda point: float(point["value"]))
        if float(hottest["value"]) < HOT_THRESHOLD:
            continue
        output.append(
            {
                **scene,
                "peakSeconds": round(midpoint(hottest)),
                "peakValue": round(float(hottest["value"]), 6),
            }
        )
    return output


def main() -> int:
    videos = load_json(VIDEOS_PATH, [])
    chapters = load_json(CHAPTERS_PATH, {})
    heatmaps = load_json(HEATMAPS_PATH, {})
    if not isinstance(videos, list) or not isinstance(chapters, dict) or not isinstance(heatmaps, dict):
        raise RuntimeError("Generated video, chapter, or heatmap data is invalid")
    videos_by_id = {
        str(video.get("youtubeId")): video
        for video in videos
        if isinstance(video, dict) and VIDEO_ID_RE.fullmatch(str(video.get("youtubeId") or ""))
    }

    full_ids = {
        path.stem for path in SUBTITLES_DIR.glob("*.vtt") if VIDEO_ID_RE.fullmatch(path.stem)
    } & set(videos_by_id)
    partial_ids = {
        path.stem for path in PARTIAL_SUBTITLES_DIR.glob("*.vtt") if VIDEO_ID_RE.fullmatch(path.stem)
    } & set(videos_by_id) - full_ids
    coverage: dict[str, dict[str, Any]] = {}
    for video_id in sorted(full_ids):
        coverage[video_id] = {
            "coverage": "full",
            "subtitlePath": f"subtitles/{video_id}.vtt",
            "ranges": [],
        }

    partial_scenes: dict[str, list[dict[str, Any]]] = {}
    for video_id in sorted(partial_ids):
        cue_ranges = parse_vtt_ranges(PARTIAL_SUBTITLES_DIR / f"{video_id}.vtt")
        scenes = normalize_partial_scenes(
            video_id, load_json(PARTIAL_SCENES_DIR / f"{video_id}.json", None), cue_ranges
        )
        partial_scenes[video_id] = scenes
        coverage[video_id] = {
            "coverage": "highlights",
            "subtitlePath": f"highlight-subtitles/{video_id}.vtt",
            "ranges": [
                {"startSeconds": scene["startSeconds"], "endSeconds": scene["endSeconds"]}
                for scene in scenes
            ],
        }

    highlights: list[dict[str, Any]] = []
    for video_id, coverage_entry in coverage.items():
        video = videos_by_id.get(video_id)
        points = heatmaps.get(video_id)
        if not video or not isinstance(points, list) or not points:
            continue
        if coverage_entry["coverage"] == "full":
            video_chapters = chapters.get(video_id)
            if not isinstance(video_chapters, list):
                continue
            scenes = hot_scenes_from_chapters(video_chapters, points)
        else:
            scenes = hot_partial_scenes(partial_scenes[video_id], points)
        if not scenes:
            continue
        metadata = load_metadata(video_id, video)
        highlights.append(
            {
                "youtubeId": video_id,
                "date": metadata["date"],
                "displayTitle": metadata["displayTitle"],
                "originalTitle": metadata["originalTitle"],
                "coverage": coverage_entry["coverage"],
                "subtitlePath": coverage_entry["subtitlePath"],
                "scenes": scenes,
            }
        )

    video_order = {str(video.get("youtubeId")): index for index, video in enumerate(videos) if isinstance(video, dict)}
    highlights.sort(key=lambda item: video_order.get(item["youtubeId"], len(video_order)))
    atomic_write_json(COVERAGE_PATH, coverage)
    atomic_write_json(HIGHLIGHTS_PATH, highlights)
    print(f"Updated {COVERAGE_PATH.relative_to(ROOT)} for {len(coverage)} video(s).")
    print(
        f"Updated {HIGHLIGHTS_PATH.relative_to(ROOT)} with "
        f"{sum(len(item['scenes']) for item in highlights)} scene(s) from {len(highlights)} video(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
