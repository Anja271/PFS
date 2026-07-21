#!/usr/bin/env python3
"""Prepare one official finished PLAVE livestream in a single approved run.

The script downloads metadata and Korean caption JSON only; it never downloads
video or audio. All files stay in the ignored .subtitle-work directory. This is
the only network-bearing preparation command needed by the translation phase.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


ROOT = Path(__file__).resolve().parents[1]
VIDEOS_PATH = ROOT / "data" / "videos.json"
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
OFFICIAL_UPLOADER = "@plave_official"
HOT_THRESHOLD = 0.5
CONTEXT_PADDING_SECONDS = 90
MERGE_GAP_SECONDS = 120


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def load_official_videos() -> list[dict[str, Any]]:
    try:
        raw = json.loads(VIDEOS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("data/videos.json is not readable valid JSON") from error
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("data/videos.json must be a non-empty list")
    videos = [
        item
        for item in raw
        if isinstance(item, dict) and VIDEO_ID_RE.fullmatch(str(item.get("youtubeId") or ""))
    ]
    if not videos:
        raise RuntimeError("data/videos.json contains no valid official stream IDs")
    return videos


def parse_target(value: str, videos: list[dict[str, Any]]) -> list[str]:
    if value == "latest":
        return [str(item["youtubeId"]) for item in videos]
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,20})", value)
    video_id = match.group(1) if match else value
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise RuntimeError("target is not a valid YouTube video ID or URL")
    if video_id not in {str(item["youtubeId"]) for item in videos}:
        raise RuntimeError("target is not listed in the official PLAVE /streams data")
    return [video_id]


def extract_info(ydl: YoutubeDL, video_id: str) -> dict[str, Any]:
    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    if not isinstance(info, dict):
        raise RuntimeError("yt-dlp returned no usable metadata")
    if str(info.get("uploader_id") or "").lower() != OFFICIAL_UPLOADER:
        raise RuntimeError("video does not belong to the official PLAVE channel")
    return info


def is_finished(info: dict[str, Any]) -> bool:
    status = str(info.get("live_status") or "").lower()
    return not bool(info.get("is_live")) and status not in {"is_live", "is_upcoming", "post_live"}


def korean_json3_track(info: dict[str, Any]) -> dict[str, Any] | None:
    for collection_name in ("subtitles", "automatic_captions"):
        collection = info.get(collection_name)
        if not isinstance(collection, dict):
            continue
        languages = [key for key in collection if str(key).lower() == "ko"]
        languages += [
            key
            for key in collection
            if str(key).lower().startswith("ko-") and key not in languages
        ]
        for language in languages:
            tracks = collection.get(language)
            if not isinstance(tracks, list):
                continue
            track = next(
                (
                    item
                    for item in tracks
                    if isinstance(item, dict)
                    and item.get("ext") == "json3"
                    and isinstance(item.get("url"), str)
                ),
                None,
            )
            if track:
                return {**track, "language": str(language), "source": collection_name}
    return None


def download_json3(ydl: YoutubeDL, track: dict[str, Any]) -> dict[str, Any]:
    with ydl.urlopen(track["url"]) as response:
        payload = response.read()
    try:
        parsed = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Korean caption response is not valid UTF-8 JSON3") from error
    if not isinstance(parsed, dict) or not isinstance(parsed.get("events"), list):
        raise RuntimeError("Korean caption JSON3 contains no events")
    return parsed


def timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.000"


def source_cues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: OrderedDict[int, list[str]] = OrderedDict()
    for event in payload.get("events", []):
        if not isinstance(event, dict) or isinstance(event.get("tStartMs"), bool):
            continue
        start_ms = event.get("tStartMs")
        if not isinstance(start_ms, (int, float)) or not math.isfinite(float(start_ms)) or start_ms < 0:
            continue
        text = "".join(
            str(segment.get("utf8") or "")
            for segment in event.get("segs", [])
            if isinstance(segment, dict)
        ).replace("\n", " ").strip()
        if text:
            grouped.setdefault(int(start_ms // 1000), []).append(text)
    cues = [
        {
            "startSeconds": start,
            "start": timestamp(start),
            "sourceParts": parts,
            "source": " ".join(parts),
            "translation": "",
        }
        for start, parts in grouped.items()
    ]
    if not cues or [cue["startSeconds"] for cue in cues] != sorted(
        {cue["startSeconds"] for cue in cues}
    ):
        raise RuntimeError("caption normalization did not produce strictly increasing unique cues")
    return cues


def normalized_heatmap(raw: Any) -> list[dict[str, float]]:
    if not isinstance(raw, list):
        return []
    points: list[dict[str, float]] = []
    previous = -1.0
    for item in raw:
        if not isinstance(item, dict):
            return []
        values = (item.get("start_time"), item.get("end_time"), item.get("value"))
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            return []
        start, end, value = map(float, values)
        if (
            not all(math.isfinite(number) for number in (start, end, value))
            or start < 0
            or end <= start
            or start <= previous
            or not 0 <= value <= 1
        ):
            return []
        points.append(
            {
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
                "value": round(value, 6),
            }
        )
        previous = start
    return points


def scene_plan(points: list[dict[str, float]], cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hot = [point for point in points if point["value"] >= HOT_THRESHOLD]
    if not hot:
        return []
    clusters: list[dict[str, float]] = []
    for point in hot:
        start = max(0.0, point["startSeconds"] - CONTEXT_PADDING_SECONDS)
        end = point["endSeconds"] + CONTEXT_PADDING_SECONDS
        if clusters and start <= clusters[-1]["endSeconds"] + MERGE_GAP_SECONDS:
            clusters[-1]["endSeconds"] = max(clusters[-1]["endSeconds"], end)
            clusters[-1]["peakValue"] = max(clusters[-1]["peakValue"], point["value"])
        else:
            clusters.append(
                {"startSeconds": start, "endSeconds": end, "peakValue": point["value"]}
            )
    starts = [int(cue["startSeconds"]) for cue in cues]
    plan: list[dict[str, Any]] = []
    for number, cluster in enumerate(clusters, start=1):
        eligible_starts = [start for start in starts if start >= math.floor(cluster["startSeconds"])]
        if not eligible_starts:
            continue
        start = eligible_starts[0]
        later = [value for value in starts if value > math.ceil(cluster["endSeconds"])]
        end = later[0] if later else starts[-1] + 6
        plan.append(
            {
                "scene": number,
                "contextStartSeconds": start,
                "contextEndSeconds": end,
                "peakValue": round(cluster["peakValue"], 6),
                "independenceStatus": "requires-context-review",
                "parallelEligible": False,
                "note": (
                    "This padded heatmap range is discovery input, not a final subtitle boundary. "
                    "Read wider context and replace it with complete semantic scene boundaries. "
                    "Set parallelEligible only after confirming that no conversation, call, game, "
                    "story, role-play, question-answer exchange, or running joke crosses it."
                ),
            }
        )
    return plan


def normalized_date(info: dict[str, Any]) -> str:
    for key in ("upload_date", "release_date"):
        value = info.get(key)
        if isinstance(value, str) and re.fullmatch(r"\d{8}", value):
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return ""


def prepare(video_id: str, info: dict[str, Any], ydl: YoutubeDL, mode: str) -> Path:
    track = korean_json3_track(info)
    if track is None:
        raise RuntimeError("finished stream has no Korean JSON3 caption track yet")
    raw_captions = download_json3(ydl, track)
    cues = source_cues(raw_captions)
    heatmap = normalized_heatmap(info.get("heatmap"))
    work = WORK_ROOT / video_id
    work.mkdir(parents=True, exist_ok=True)
    (work / "source.ko.json3").write_text(
        json.dumps(raw_captions, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    atomic_write_json(work / "source-cues.json", cues)
    atomic_write_json(work / "heatmap.json", heatmap)
    metadata = {
        "youtubeId": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": str(info.get("title") or "").strip(),
        "date": normalized_date(info),
        "durationSeconds": int(float(info.get("duration") or 0)),
        "uploaderId": str(info.get("uploader_id") or ""),
        "liveStatus": str(info.get("live_status") or "not_live"),
        "captionLanguage": track["language"],
        "captionSource": track["source"],
        "sourceCueCount": len(cues),
        "heatmapPointCount": len(heatmap),
    }
    atomic_write_json(work / "metadata.json", metadata)
    plan = scene_plan(heatmap, cues) if mode == "highlights" else []
    atomic_write_json(work / "scene-plan.json", plan)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = {
        "version": 1,
        "youtubeId": video_id,
        "mode": mode,
        "status": "prepared",
        "preparedAt": now,
        "sourceCueCount": len(cues),
        "scenePlanCount": len(plan),
        "networkPreparationComplete": True,
        "publicationApproved": False,
        "nextAction": "Translate locally, run the independent context review, then finalize locally.",
    }
    atomic_write_json(work / "job-state.json", state)
    return work


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="latest, an official PLAVE video ID, or its YouTube URL")
    parser.add_argument("--mode", choices=("full", "highlights"), default="full")
    args = parser.parse_args()
    videos = load_official_videos()
    candidates = parse_target(args.target, videos)
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "js_runtimes": {"node": {}},
    }
    errors: list[str] = []
    with YoutubeDL(options) as ydl:
        for video_id in candidates:
            try:
                info = extract_info(ydl, video_id)
                if not is_finished(info):
                    if args.target == "latest":
                        continue
                    raise RuntimeError("stream is still live, upcoming, or post-live processing")
                work = prepare(video_id, info, ydl, args.mode)
                print(
                    f"Prepared {video_id} in {work.relative_to(ROOT)}: "
                    f"metadata, Korean captions, source cues, heatmap, and job state."
                )
                return 0
            except Exception as error:
                if args.target != "latest":
                    raise
                errors.append(f"{video_id}: {error}")
                if len(errors) >= 12:
                    break
    detail = "; ".join(errors[:3])
    raise RuntimeError(f"no recent finished stream with Korean captions was ready ({detail})")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}")
        raise SystemExit(1)
