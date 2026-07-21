#!/usr/bin/env python3
"""Build a non-public priority preview for PLAVE highlight scanning.

The existing candidate queue is deliberately not modified. Current public view
counts are read with one flat yt-dlp request to the official /streams tab. A
video is compared only with nearby uploads, which limits channel-growth and age
bias. Editorial legendary evidence, a protected recent-backlog lane, and an
archive-discovery lane are then combined into a starvation-resistant preview.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


ROOT = Path(__file__).resolve().parents[1]
STREAMS_URL = "https://www.youtube.com/@plave_official/streams"
VIDEOS_PATH = ROOT / "data" / "videos.json"
LEGENDARY_PATH = ROOT / "data" / "legendary-streams.json"
SCAN_STATE_PATH = ROOT / "data" / "highlight-scan-state.json"
OUTPUT_PATH = ROOT / "data" / "stream-priority-preview.json"
SUBTITLES_DIR = ROOT / "subtitles"
HIGHLIGHT_SUBTITLES_DIR = ROOT / "highlight-subtitles"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
COHORT_RADIUS = 10
RECENT_WINDOW = 24
LANE_PATTERN = ("priority", "priority", "recent", "priority", "archive", "recent")


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return fallback


def atomic_write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def official_videos() -> list[dict[str, Any]]:
    raw = load_json(VIDEOS_PATH, None)
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("data/videos.json must be a non-empty list")
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
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
                "playlistIndex": index,
            }
        )
    if not videos:
        raise RuntimeError("data/videos.json contains no valid official stream IDs")
    return videos


def flat_view_counts() -> dict[str, int]:
    options = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "js_runtimes": {"node": {}},
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(STREAMS_URL, download=False)
    entries = info.get("entries") if isinstance(info, dict) else None
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("yt-dlp returned no flat /streams entries")
    counts: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "")
        view_count = entry.get("view_count")
        if (
            VIDEO_ID_RE.fullmatch(video_id)
            and not isinstance(view_count, bool)
            and isinstance(view_count, (int, float))
            and math.isfinite(float(view_count))
            and view_count >= 0
        ):
            counts[video_id] = int(view_count)
    if not counts:
        raise RuntimeError("the flat /streams response contained no usable view counts")
    return counts


def legendary_entries(known_ids: set[str]) -> dict[str, dict[str, Any]]:
    raw = load_json(LEGENDARY_PATH, None)
    if not isinstance(raw, list):
        raise RuntimeError("data/legendary-streams.json must be a list")
    output: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise RuntimeError("every legendary-stream entry must be an object")
        video_id = str(item.get("youtubeId") or "")
        score = item.get("legendaryScore")
        evidence = item.get("evidence")
        if (
            video_id not in known_ids
            or video_id in output
            or isinstance(score, bool)
            or not isinstance(score, int)
            or not 0 <= score <= 100
            or not isinstance(item.get("reason"), str)
            or not str(item.get("reason")).strip()
            or not isinstance(item.get("confidence"), str)
            or not isinstance(evidence, list)
            or not all(isinstance(value, str) and value.strip() for value in evidence)
        ):
            raise RuntimeError(f"invalid legendary-stream entry for {video_id or '<missing ID>'}")
        output[video_id] = item
    return output


def percentile(value: int | None, comparison: list[int]) -> float:
    if value is None or not comparison:
        return 0.5
    below = sum(candidate < value for candidate in comparison)
    equal = sum(candidate == value for candidate in comparison)
    return round((below + max(0, equal - 1) / 2) / max(1, len(comparison) - 1), 4)


def coverage(video_id: str) -> str:
    if (SUBTITLES_DIR / f"{video_id}.vtt").is_file():
        return "full"
    if (HIGHLIGHT_SUBTITLES_DIR / f"{video_id}.vtt").is_file():
        return "highlights"
    return "none"


def ranked_records(
    videos: list[dict[str, Any]], counts: dict[str, int], legendary: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    state = load_json(SCAN_STATE_PATH, {})
    state_videos = state.get("videos", {}) if isinstance(state, dict) else {}
    if not isinstance(state_videos, dict):
        state_videos = {}
    total = len(videos)
    records: list[dict[str, Any]] = []
    for index, video in enumerate(videos):
        video_id = video["youtubeId"]
        if coverage(video_id) != "none":
            continue
        start = max(0, index - COHORT_RADIUS)
        end = min(total, index + COHORT_RADIUS + 1)
        cohort = [
            counts[item["youtubeId"]]
            for item in videos[start:end]
            if item["youtubeId"] in counts
        ]
        cohort_percentile = percentile(counts.get(video_id), cohort)
        archive_percentile = round(index / max(1, total - 1), 4)
        legend = legendary.get(video_id, {})
        legendary_score = int(legend.get("legendaryScore") or 0)
        # No time-dependent view velocity is used. Age has deliberately low
        # weight; recent coverage is guaranteed by a separate selection lane.
        score = round(
            55 * (legendary_score / 100)
            + 35 * cohort_percentile
            + 10 * archive_percentile,
            3,
        )
        scan_entry = state_videos.get(video_id)
        scan_status = str(scan_entry.get("status") or "not_scanned") if isinstance(scan_entry, dict) else "not_scanned"
        records.append(
            {
                "youtubeId": video_id,
                "title": video["title"],
                "playlistIndex": index,
                "viewCount": counts.get(video_id),
                "cohortViewPercentile": cohort_percentile,
                "archivePercentile": archive_percentile,
                "legendaryScore": legendary_score,
                "legendaryConfidence": legend.get("confidence", "unresearched"),
                "legendaryReason": legend.get("reason", ""),
                "score": score,
                "knownScanStatus": scan_status,
            }
        )
    return records


def interleave(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = sorted(
        records,
        key=lambda item: (-item["score"], -item["cohortViewPercentile"], item["playlistIndex"]),
    )
    recent = sorted(
        (item for item in records if item["playlistIndex"] < RECENT_WINDOW),
        key=lambda item: (-item["cohortViewPercentile"], item["playlistIndex"]),
    )
    archive_start = math.floor(max((item["playlistIndex"] for item in records), default=0) * 2 / 3)
    archive = sorted(
        (item for item in records if item["playlistIndex"] >= archive_start),
        key=lambda item: (-item["score"], -item["cohortViewPercentile"], -item["playlistIndex"]),
    )
    pools = {"priority": priority, "recent": recent, "archive": archive}
    selected: set[str] = set()
    ordered: list[dict[str, Any]] = []
    pattern_index = 0
    while len(ordered) < len(records):
        lane = LANE_PATTERN[pattern_index % len(LANE_PATTERN)]
        pattern_index += 1
        pool = pools[lane]
        candidate = next((item for item in pool if item["youtubeId"] not in selected), None)
        if candidate is None:
            candidate = next(item for item in priority if item["youtubeId"] not in selected)
            lane = "priority-fallback"
        selected.add(candidate["youtubeId"])
        ordered.append({**candidate, "previewRank": len(ordered) + 1, "selectionLane": lane})
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="preview path; the live candidate queue is never modified",
    )
    args = parser.parse_args()
    videos = official_videos()
    counts = flat_view_counts()
    legendary = legendary_entries({video["youtubeId"] for video in videos})
    records = ranked_records(videos, counts, legendary)
    ordered = interleave(records)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = {
        "version": 1,
        "generatedAt": now,
        "source": STREAMS_URL,
        "modifiesLiveQueue": False,
        "method": {
            "cohortRadius": COHORT_RADIUS,
            "recentWindow": RECENT_WINDOW,
            "lanePattern": list(LANE_PATTERN),
            "scoreWeights": {
                "legendaryEvidence": 0.55,
                "cohortViewPercentile": 0.35,
                "archiveDiscovery": 0.1,
                "longTermViewVelocity": 0,
            },
        },
        "eligibleUntranslatedStreams": len(ordered),
        "entries": ordered,
    }
    atomic_write_json(args.output, result)
    print(f"Wrote {len(ordered)} untranslated streams to {args.output}")
    for item in ordered[:20]:
        print(
            f"{item['previewRank']:>2}. {item['selectionLane']:<17} "
            f"{item['youtubeId']} score={item['score']:>6.3f} "
            f"views={item['viewCount']} cohort={item['cohortViewPercentile']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
