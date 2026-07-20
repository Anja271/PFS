#!/usr/bin/env python3
"""Discover older PLAVE livestreams that can supply subtitled highlights.

The scanner reads only video IDs already present in data/videos.json, whose
source is the official @plave_official/streams tab. It asks yt-dlp for metadata,
automatic-caption availability, and YouTube's optional replay heatmap. No video
or audio media is downloaded.

Results are deliberately separate from data/highlights.json. A candidate does
not become public until its scene boundaries and English fan subtitles have
been reviewed and published through scripts/update_highlights.py.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


ROOT = Path(__file__).resolve().parents[1]
VIDEOS_PATH = ROOT / "data" / "videos.json"
HIGHLIGHTS_PATH = ROOT / "data" / "highlights.json"
STATE_PATH = ROOT / "data" / "highlight-scan-state.json"
CANDIDATES_PATH = ROOT / "data" / "highlight-candidates.json"
SUBTITLES_DIR = ROOT / "subtitles"
PARTIAL_SUBTITLES_DIR = ROOT / "highlight-subtitles"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
HOT_THRESHOLD = 0.5
RETRYABLE_STATUSES = {"no_heatmap", "no_korean_captions", "processing", "error"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


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


def load_videos() -> list[dict[str, str]]:
    raw = load_json(VIDEOS_PATH, None)
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("data/videos.json must be a non-empty list")
    videos: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("youtubeId") or "")
        if not VIDEO_ID_RE.fullmatch(video_id) or video_id in seen:
            continue
        seen.add(video_id)
        videos.append(
            {
                "youtubeId": video_id,
                "title": str(item.get("title") or "").strip(),
                "publishedAt": str(item.get("publishedAt") or "").strip(),
            }
        )
    if not videos:
        raise RuntimeError("data/videos.json contains no valid video IDs")
    return videos


def normalize_heatmap(raw: Any) -> list[dict[str, float]] | None:
    if not isinstance(raw, list) or not raw:
        return None
    output: list[dict[str, float]] = []
    previous_start = -1.0
    for point in raw:
        if not isinstance(point, dict):
            return None
        values = (point.get("start_time"), point.get("end_time"), point.get("value"))
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            return None
        start, end, value = map(float, values)
        if (
            not all(math.isfinite(number) for number in (start, end, value))
            or start < 0
            or end <= start
            or start <= previous_start
            or not 0 <= value <= 1
        ):
            return None
        output.append(
            {
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
                "value": round(value, 6),
            }
        )
        previous_start = start
    return output


def hot_clusters(points: list[dict[str, float]]) -> list[dict[str, float | int]]:
    hot = [point for point in points if point["value"] >= HOT_THRESHOLD]
    if not hot:
        return []
    groups: list[list[dict[str, float]]] = []
    for point in hot:
        if groups and point["startSeconds"] <= groups[-1][-1]["endSeconds"] + 0.01:
            groups[-1].append(point)
        else:
            groups.append([point])
    clusters: list[dict[str, float | int]] = []
    for group in groups:
        peak = max(group, key=lambda point: point["value"])
        clusters.append(
            {
                "startSeconds": round(group[0]["startSeconds"]),
                "endSeconds": round(group[-1]["endSeconds"]),
                "peakSeconds": round(
                    peak["startSeconds"] + (peak["endSeconds"] - peak["startSeconds"]) / 2
                ),
                "peakValue": peak["value"],
            }
        )
    return clusters


def has_korean_captions(info: dict[str, Any]) -> bool:
    for key in ("automatic_captions", "subtitles"):
        tracks = info.get(key)
        if not isinstance(tracks, dict):
            continue
        if any(str(language).lower() == "ko" or str(language).lower().startswith("ko-") for language in tracks):
            return True
    return False


def normalize_date(info: dict[str, Any], fallback: str) -> str:
    for key in ("upload_date", "release_date"):
        value = info.get(key)
        if isinstance(value, str) and re.fullmatch(r"\d{8}", value):
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return fallback


def extract_candidate(video_id: str) -> dict[str, Any]:
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "js_runtimes": {"node": {}},
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    if not isinstance(info, dict):
        raise RuntimeError("yt-dlp returned no usable metadata")
    return info


def parse_checked_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def should_scan(entry: Any, now: datetime, retry_after: timedelta, force: bool) -> bool:
    if force or not isinstance(entry, dict):
        return True
    status = entry.get("status")
    if status in {"ready", "published", "unavailable"}:
        return False
    if status not in RETRYABLE_STATUSES:
        return True
    checked_at = parse_checked_at(entry.get("checkedAt"))
    if checked_at is None:
        return True
    error_delay = min(retry_after, timedelta(days=1))
    return now - checked_at >= (error_delay if status == "error" else retry_after)


def published_ids() -> set[str]:
    raw = load_json(HIGHLIGHTS_PATH, [])
    if not isinstance(raw, list):
        return set()
    return {
        str(item.get("youtubeId"))
        for item in raw
        if isinstance(item, dict) and VIDEO_ID_RE.fullmatch(str(item.get("youtubeId") or ""))
    }


def subtitle_coverage(video_id: str) -> str:
    if (SUBTITLES_DIR / f"{video_id}.vtt").is_file():
        return "full"
    if (PARTIAL_SUBTITLES_DIR / f"{video_id}.vtt").is_file():
        return "highlights"
    return "none"


def classify(video: dict[str, str], info: dict[str, Any], checked_at: str) -> dict[str, Any]:
    video_id = video["youtubeId"]
    title = str(info.get("title") or video["title"]).strip()
    base = {
        "status": "error",
        "checkedAt": checked_at,
        "title": title,
        "publishedAt": normalize_date(info, video["publishedAt"]),
        "subtitleCoverage": subtitle_coverage(video_id),
    }
    live_status = str(info.get("live_status") or "").lower()
    if live_status in {"is_live", "is_upcoming", "post_live"}:
        return {**base, "status": "processing", "liveStatus": live_status}
    availability = str(info.get("availability") or "public").lower()
    if availability in {"private", "subscriber_only", "needs_auth", "premium_only"}:
        return {**base, "status": "unavailable", "availability": availability}

    points = normalize_heatmap(info.get("heatmap"))
    korean_captions = has_korean_captions(info)
    if not points:
        return {**base, "status": "no_heatmap", "hasKoreanCaptions": korean_captions}
    if not korean_captions and base["subtitleCoverage"] == "none":
        return {
            **base,
            "status": "no_korean_captions",
            "hasKoreanCaptions": False,
            "heatmapPoints": len(points),
        }
    clusters = hot_clusters(points)
    return {
        **base,
        "status": "ready",
        "hasKoreanCaptions": korean_captions,
        "heatmapPoints": len(points),
        "hotClusters": clusters,
    }


def build_candidates(videos: list[dict[str, str]], state_entries: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for video in videos:
        video_id = video["youtubeId"]
        entry = state_entries.get(video_id)
        if not isinstance(entry, dict) or entry.get("status") != "ready":
            continue
        candidates.append(
            {
                "youtubeId": video_id,
                "title": str(entry.get("title") or video["title"]),
                "publishedAt": str(entry.get("publishedAt") or video["publishedAt"]),
                "subtitleCoverage": str(entry.get("subtitleCoverage") or "none"),
                "checkedAt": str(entry.get("checkedAt") or ""),
                "heatmapPoints": int(entry.get("heatmapPoints") or 0),
                "hotClusters": entry.get("hotClusters") if isinstance(entry.get("hotClusters"), list) else [],
            }
        )
    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5, help="maximum videos to inspect this run")
    parser.add_argument(
        "--retry-after-days",
        type=int,
        default=30,
        help="days before retrying a normal no-data result",
    )
    parser.add_argument("--force", action="store_true", help="ignore saved retry dates")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.limit > 50:
        raise RuntimeError("--limit must be between 1 and 50")
    if args.retry_after_days < 1 or args.retry_after_days > 365:
        raise RuntimeError("--retry-after-days must be between 1 and 365")

    videos = load_videos()
    raw_state = load_json(STATE_PATH, {})
    entries = raw_state.get("videos", {}) if isinstance(raw_state, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    known_ids = {video["youtubeId"] for video in videos}
    entries = {video_id: entry for video_id, entry in entries.items() if video_id in known_ids}
    original_entries = copy.deepcopy(entries)

    now = utc_now()
    checked_at = now.isoformat().replace("+00:00", "Z")
    published = published_ids()
    for video in videos:
        video_id = video["youtubeId"]
        if video_id in published:
            published_entry = {
                "status": "published",
                "title": video["title"],
                "publishedAt": video["publishedAt"],
                "subtitleCoverage": subtitle_coverage(video_id),
            }
            current = entries.get(video_id)
            comparable = (
                {key: value for key, value in current.items() if key != "checkedAt"}
                if isinstance(current, dict)
                else None
            )
            if comparable != published_entry:
                entries[video_id] = {**published_entry, "checkedAt": checked_at}

    attempted = 0
    for video in videos:
        if attempted >= args.limit:
            break
        video_id = video["youtubeId"]
        if video_id in published or not should_scan(
            entries.get(video_id), now, timedelta(days=args.retry_after_days), args.force
        ):
            continue
        attempted += 1
        print(f"[{attempted}/{args.limit}] Checking {video_id}: {video['title']}")
        try:
            info = extract_candidate(video_id)
            entries[video_id] = classify(video, info, checked_at)
        except Exception as error:
            entries[video_id] = {
                "status": "error",
                "checkedAt": checked_at,
                "title": video["title"],
                "publishedAt": video["publishedAt"],
                "subtitleCoverage": subtitle_coverage(video_id),
                "error": str(error).strip()[:500] or error.__class__.__name__,
            }
        print(f"  -> {entries[video_id]['status']}")

    candidates = build_candidates(videos, entries)
    counts: dict[str, int] = {}
    for entry in entries.values():
        if isinstance(entry, dict):
            status = str(entry.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    state_changed = entries != original_entries
    previous_updated_at = raw_state.get("updatedAt", "") if isinstance(raw_state, dict) else ""
    state = {
        "version": 1,
        "updatedAt": checked_at if state_changed else previous_updated_at,
        "retryAfterDays": args.retry_after_days,
        "videos": entries,
    }
    atomic_write_json(STATE_PATH, state)
    atomic_write_json(CANDIDATES_PATH, candidates)
    print(f"Inspected {attempted} video(s); {len(candidates)} candidate(s) are ready.")
    print("Status totals: " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
