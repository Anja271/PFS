#!/usr/bin/env python3
"""Prepare Korean and English YouTube captions for a local VLAST-caption pilot.

This command validates the official, finished PLAVE upload and downloads only
caption JSON plus metadata. It never downloads video or audio. Raw and
normalized caption bodies are written outside the repository so they can be
deleted after the one-time editorial pilot.
"""

from __future__ import annotations

import argparse
import hashlib
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
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
OFFICIAL_UPLOADER = "@plave_official"


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def parse_video_id(value: str) -> str:
    match = re.search(
        r"(?:v=|youtu\.be/|youtube\.com/live/)([A-Za-z0-9_-]{6,20})", value
    )
    video_id = match.group(1) if match else value
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise RuntimeError("target is not a valid YouTube video ID or URL")
    return video_id


def extract_info(ydl: YoutubeDL, video_id: str) -> dict[str, Any]:
    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    if not isinstance(info, dict):
        raise RuntimeError("yt-dlp returned no usable metadata")
    if str(info.get("uploader_id") or "").lower() != OFFICIAL_UPLOADER:
        raise RuntimeError("video does not belong to the official PLAVE channel")
    status = str(info.get("live_status") or "").lower()
    if bool(info.get("is_live")) or status in {"is_live", "is_upcoming", "post_live"}:
        raise RuntimeError("stream is still live, upcoming, or post-live processing")
    return info


def language_keys(collection: Any, base: str) -> list[str]:
    if not isinstance(collection, dict):
        return []
    exact = [key for key in collection if str(key).lower() == base]
    regional = [
        key
        for key in collection
        if str(key).lower().startswith(f"{base}-") and key not in exact
    ]
    return [str(key) for key in exact + regional]


def select_track(info: dict[str, Any], base: str) -> dict[str, Any] | None:
    # A channel-supplied subtitle is preferred. Automatic captions remain a
    # fallback for Korean because older official streams expose only that form.
    for source in ("subtitles", "automatic_captions"):
        collection = info.get(source)
        if not isinstance(collection, dict):
            continue
        for language in language_keys(collection, base):
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
                return {**track, "language": language, "source": source}
    return None


def download_json3(ydl: YoutubeDL, track: dict[str, Any], label: str) -> tuple[dict[str, Any], bytes]:
    with ydl.urlopen(track["url"]) as response:
        payload = response.read()
    try:
        parsed = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} caption response is not valid UTF-8 JSON3") from error
    if not isinstance(parsed, dict) or not isinstance(parsed.get("events"), list):
        raise RuntimeError(f"{label} caption JSON3 contains no events")
    return parsed, payload


def normalize_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or isinstance(event.get("tStartMs"), bool):
            continue
        start = event.get("tStartMs")
        duration = event.get("dDurationMs", 0)
        if not isinstance(start, (int, float)) or not math.isfinite(float(start)) or start < 0:
            continue
        if not isinstance(duration, (int, float)) or not math.isfinite(float(duration)):
            duration = 0
        segments = []
        for segment in event.get("segs", []):
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("utf8") or "")
            if not text:
                continue
            segments.append(
                {
                    "offsetMs": int(segment.get("tOffsetMs") or 0),
                    "text": text,
                }
            )
        text = "".join(segment["text"] for segment in segments).replace("\n", " ").strip()
        if not text:
            continue
        normalized.append(
            {
                "startMs": int(start),
                "durationMs": max(0, int(duration)),
                "windowId": event.get("wWinId"),
                "append": bool(event.get("aAppend")),
                "text": text,
                "segments": segments,
            }
        )
    if not normalized:
        raise RuntimeError("caption normalization produced no text events")
    return normalized


def normalized_date(info: dict[str, Any]) -> str:
    for key in ("upload_date", "release_date"):
        value = info.get(key)
        if isinstance(value, str) and re.fullmatch(r"\d{8}", value):
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return ""


def track_summary(track: dict[str, Any], event_count: int, digest: str) -> dict[str, Any]:
    return {
        "language": track["language"],
        "source": track["source"],
        "name": str(track.get("name") or ""),
        "eventCount": event_count,
        "sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="an official PLAVE YouTube video ID or URL")
    parser.add_argument(
        "--temporary-root",
        type=Path,
        help="outside-repository directory for temporary caption bodies",
    )
    args = parser.parse_args()
    video_id = parse_video_id(args.target)
    temporary_root = (args.temporary_root or Path("/tmp") / f"plave-vlast-pilot-{video_id}").resolve()
    try:
        temporary_root.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise RuntimeError("temporary caption bodies must be stored outside the repository")

    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "js_runtimes": {"node": {}},
    }
    with YoutubeDL(options) as ydl:
        info = extract_info(ydl, video_id)
        korean_track = select_track(info, "ko")
        english_track = select_track(info, "en")
        if korean_track is None:
            raise RuntimeError("finished stream has no usable Korean JSON3 caption track")
        if english_track is None:
            raise RuntimeError("finished stream has no usable English JSON3 caption track")
        korean_raw, korean_bytes = download_json3(ydl, korean_track, "Korean")
        english_raw, english_bytes = download_json3(ydl, english_track, "English")

    korean_events = normalize_events(korean_raw)
    english_events = normalize_events(english_raw)
    temporary_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(temporary_root / "korean-events.json", korean_events)
    atomic_write_json(temporary_root / "english-events.json", english_events)
    (temporary_root / "source.ko.json3").write_bytes(korean_bytes)
    (temporary_root / "source.en.json3").write_bytes(english_bytes)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    work = WORK_ROOT / video_id / "vlast-assisted"
    metadata = {
        "version": 1,
        "youtubeId": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": str(info.get("title") or "").strip(),
        "date": normalized_date(info),
        "durationSeconds": int(float(info.get("duration") or 0)),
        "uploaderId": str(info.get("uploader_id") or ""),
        "liveStatus": str(info.get("live_status") or "not_live"),
        "preparedAt": now,
        "temporarySourceDirectory": str(temporary_root),
        "koreanTrack": track_summary(
            korean_track, len(korean_events), hashlib.sha256(korean_bytes).hexdigest()
        ),
        "englishTrack": track_summary(
            english_track, len(english_events), hashlib.sha256(english_bytes).hexdigest()
        ),
        "availableSubtitleLanguages": sorted(
            str(key) for key in (info.get("subtitles") or {}).keys()
        ),
        "availableAutomaticCaptionLanguages": sorted(
            str(key) for key in (info.get("automatic_captions") or {}).keys()
        ),
        "mediaDownloaded": False,
        "publicationApproved": False,
    }
    atomic_write_json(work / "pilot-metadata.json", metadata)
    progress_path = work / "translation-progress.json"
    if not progress_path.exists():
        atomic_write_json(
            progress_path,
            {
                "version": 1,
                "youtubeId": video_id,
                "workflow": "vlast-assisted-pilot",
                "status": "sources-prepared",
                "updatedAt": now,
                "decisions": [],
                "speakerNotes": [],
                "uncertainties": [],
                "reviewSamples": [],
            },
        )
    print(
        f"Prepared VLAST-caption pilot sources for {video_id}: "
        f"{len(korean_events)} Korean events and {len(english_events)} English events. "
        f"Temporary bodies: {temporary_root}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}")
        raise SystemExit(1)
