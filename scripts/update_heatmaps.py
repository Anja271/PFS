#!/usr/bin/env python3
"""Refresh optional YouTube "Most replayed" heatmaps for chaptered videos.

YouTube does not expose heatmaps through its public APIs. yt-dlp can sometimes
read them from the player metadata, but they are not available for every video
and may appear only after YouTube has collected enough viewing data. This
script never downloads video media. It keeps the last valid heatmap for an
individual video when extraction temporarily fails or returns no heatmap.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = ROOT / "chapters"
HEATMAPS_PATH = ROOT / "data" / "heatmaps.json"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def normalize_heatmap(raw: Any) -> list[dict[str, float]] | None:
    if not isinstance(raw, list) or not raw:
        return None

    normalized: list[dict[str, float]] = []
    previous_start = -1.0
    for point in raw:
        if not isinstance(point, dict):
            return None
        start = point.get("start_time")
        end = point.get("end_time")
        value = point.get("value")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or isinstance(value, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not isinstance(value, (int, float))
        ):
            return None
        start = float(start)
        end = float(end)
        value = float(value)
        if (
            not all(math.isfinite(number) for number in (start, end, value))
            or start < 0
            or end <= start
            or start <= previous_start
            or value < 0
            or value > 1
        ):
            return None
        normalized.append(
            {
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
                "value": round(value, 6),
            }
        )
        previous_start = start
    return normalized


def load_existing_manifest() -> dict[str, list[dict[str, float]]]:
    try:
        raw = json.loads(HEATMAPS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    valid: dict[str, list[dict[str, float]]] = {}
    for video_id, points in raw.items():
        if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
            continue
        if not isinstance(points, list) or not all(isinstance(point, dict) for point in points):
            continue
        converted = [
            {
                "start_time": point.get("startSeconds"),
                "end_time": point.get("endSeconds"),
                "value": point.get("value"),
            }
            for point in points
        ]
        normalized = normalize_heatmap(converted)
        if normalized:
            valid[video_id] = normalized
    return valid


def chaptered_video_ids() -> list[str]:
    return sorted(
        path.stem
        for path in CHAPTERS_DIR.glob("*.json")
        if path.is_file() and VIDEO_ID_RE.fullmatch(path.stem)
    )


def extract_heatmap(video_id: str) -> list[dict[str, float]] | None:
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        # GitHub-hosted runners already include Node.js. Explicitly enabling it
        # keeps current yt-dlp YouTube extraction compatible without installing
        # another JavaScript runtime or adding a paid/external service.
        "js_runtimes": {"node": {}},
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    if not isinstance(info, dict):
        return None
    return normalize_heatmap(info.get("heatmap"))


def main() -> int:
    existing = load_existing_manifest()
    manifest: dict[str, list[dict[str, float]]] = {}

    for video_id in chaptered_video_ids():
        try:
            heatmap = extract_heatmap(video_id)
        except Exception as error:
            heatmap = None
            print(f"Warning: heatmap refresh failed for {video_id}: {error}")

        if heatmap:
            manifest[video_id] = heatmap
            print(f"Found {len(heatmap)} heatmap point(s) for {video_id}.")
        elif video_id in existing:
            manifest[video_id] = existing[video_id]
            print(f"No current heatmap for {video_id}; keeping the last valid data.")
        else:
            print(f"No heatmap is currently available for {video_id}.")

    atomic_write_json(HEATMAPS_PATH, manifest)
    print(f"Updated {HEATMAPS_PATH.relative_to(ROOT)} for {len(manifest)} video(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
