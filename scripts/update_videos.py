#!/usr/bin/env python3
"""Update the PLAVE Live-tab video list and local subtitle/chapter manifests.

Only CHANNEL_STREAMS_URL is passed to yt-dlp. The extractor is run in flat mode,
so no video media is downloaded. YouTube's /streams tab is already newest-first;
that source order is preserved. If yt-dlp does not expose a reliable upload or
release date, publishedAt is left empty instead of inventing a date.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_STREAMS_URL = "https://www.youtube.com/@plave_official/streams"
VIDEOS_PATH = ROOT / "data" / "videos.json"
SUBTITLES_PATH = ROOT / "data" / "subtitles.json"
SUBTITLES_DIR = ROOT / "subtitles"
CHAPTERS_PATH = ROOT / "data" / "chapters.json"
CHAPTERS_DIR = ROOT / "chapters"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
UNAVAILABLE_TITLES = {"[private video]", "[deleted video]", "private video", "deleted video"}


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def valid_existing_video_list(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, list) and bool(data) and all(
        isinstance(item, dict) and VIDEO_ID_RE.fullmatch(str(item.get("youtubeId", "")))
        for item in data
    )


def normalize_date(entry: dict[str, Any]) -> str:
    for key in ("upload_date", "release_date"):
        raw = entry.get(key)
        if isinstance(raw, str) and re.fullmatch(r"\d{8}", raw):
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    for key in ("timestamp", "release_timestamp"):
        raw = entry.get(key)
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc).date().isoformat()
    return ""


def extract_videos() -> list[dict[str, str]]:
    # Keep manifest-only helpers importable from the publication workflow even
    # when its Python interpreter does not have yt-dlp installed. Network
    # extraction is the only operation that actually requires this dependency.
    try:
        from yt_dlp import YoutubeDL
    except ImportError as error:
        raise RuntimeError(
            "yt-dlp is required only for refreshing the YouTube Live-tab video list"
        ) from error

    options = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": True,
        "playlistend": None,
    }
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(CHANNEL_STREAMS_URL, download=False)

    if not isinstance(result, dict) or result.get("entries") is None:
        raise RuntimeError("yt-dlp returned no usable entries for the PLAVE Live tab")

    videos: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for entry in result["entries"]:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "")
        title = str(entry.get("title") or "").strip()
        availability = str(entry.get("availability") or "").lower()
        if (
            not VIDEO_ID_RE.fullmatch(video_id)
            or video_id in seen_ids
            or not title
            or title.lower() in UNAVAILABLE_TITLES
            or availability in {"private", "subscriber_only", "needs_auth", "premium_only"}
        ):
            continue

        seen_ids.add(video_id)
        videos.append(
            {
                "youtubeId": video_id,
                "title": title,
                "publishedAt": normalize_date(entry),
                # A deterministic YouTube thumbnail avoids accepting an arbitrary host
                # from extractor metadata and remains compatible with GitHub Pages.
                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    if not videos:
        raise RuntimeError("No valid public videos were found; refusing to replace videos.json")
    return videos


def update_subtitle_manifest() -> None:
    ids = sorted(
        path.stem
        for path in SUBTITLES_DIR.glob("*.vtt")
        if path.is_file() and VIDEO_ID_RE.fullmatch(path.stem)
    )
    atomic_write_json(SUBTITLES_PATH, ids)
    print(f"Updated {SUBTITLES_PATH.relative_to(ROOT)} with {len(ids)} subtitle file(s).")


def update_chapter_manifest() -> None:
    manifest: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(CHAPTERS_DIR.glob("*.json")):
        if not path.is_file() or not VIDEO_ID_RE.fullmatch(path.stem):
            continue
        try:
            raw_chapters = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid chapter file {path.relative_to(ROOT)}: {error}") from error
        if not isinstance(raw_chapters, list) or not raw_chapters:
            raise RuntimeError(f"Chapter file {path.relative_to(ROOT)} must be a non-empty list")

        subtitle_path = SUBTITLES_DIR / f"{path.stem}.vtt"
        try:
            subtitle_text = subtitle_path.read_text(encoding="utf-8")
        except OSError as error:
            raise RuntimeError(
                f"Chapter file {path.relative_to(ROOT)} has no readable matching subtitle file"
            ) from error
        cue_starts = {
            int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            for hours, minutes, seconds in re.findall(
                r"^(\d{2}):(\d{2}):(\d{2})\.000\s+-->", subtitle_text, flags=re.MULTILINE
            )
        }
        if not cue_starts:
            raise RuntimeError(f"Matching subtitle file {subtitle_path.relative_to(ROOT)} has no whole-second cues")

        chapters: list[dict[str, Any]] = []
        previous_start = -1
        for index, chapter in enumerate(raw_chapters, start=1):
            if not isinstance(chapter, dict):
                raise RuntimeError(f"Chapter {index} in {path.relative_to(ROOT)} is not an object")
            start_seconds = chapter.get("startSeconds")
            title = chapter.get("title")
            if (
                isinstance(start_seconds, bool)
                or not isinstance(start_seconds, int)
                or start_seconds < 0
                or start_seconds <= previous_start
            ):
                raise RuntimeError(
                    f"Chapter {index} in {path.relative_to(ROOT)} has an invalid or non-increasing startSeconds"
                )
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
                raise RuntimeError(f"Chapter {index} in {path.relative_to(ROOT)} has an invalid title")
            if start_seconds not in cue_starts:
                raise RuntimeError(
                    f"Chapter {index} in {path.relative_to(ROOT)} does not match a VTT cue start"
                )
            if index == 1 and start_seconds != min(cue_starts):
                raise RuntimeError(
                    f"First chapter in {path.relative_to(ROOT)} must match the first VTT cue"
                )
            previous_start = start_seconds
            chapters.append({"startSeconds": start_seconds, "title": title.strip()})
        manifest[path.stem] = chapters

    atomic_write_json(CHAPTERS_PATH, manifest)
    print(f"Updated {CHAPTERS_PATH.relative_to(ROOT)} with chapters for {len(manifest)} video(s).")


def main() -> int:
    update_subtitle_manifest()
    update_chapter_manifest()
    try:
        videos = extract_videos()
    except Exception as error:  # Preserve known-good data on temporary extractor/network failures.
        if valid_existing_video_list(VIDEOS_PATH):
            print(f"Warning: {error}. Keeping the existing non-empty videos.json.", file=sys.stderr)
            return 0
        print(f"Error: {error}. No valid existing videos.json is available.", file=sys.stderr)
        return 1

    atomic_write_json(VIDEOS_PATH, videos)
    print(f"Updated {VIDEOS_PATH.relative_to(ROOT)} with {len(videos)} livestream(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
