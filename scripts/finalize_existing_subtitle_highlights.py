#!/usr/bin/env python3
"""Validate and seal highlight boundaries that reuse an existing full VTT."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
TIMING_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def timestamp_seconds(groups: tuple[str, ...]) -> float:
    hours, minutes, seconds, milliseconds = (int(value) for value in groups)
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def parse_vtt_ranges(path: Path) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    previous_end = -1.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if "-->" not in line:
            continue
        match = TIMING_RE.fullmatch(line.strip())
        if not match:
            raise RuntimeError(f"invalid VTT timing line: {line!r}")
        start = timestamp_seconds(match.groups()[:4])
        end = timestamp_seconds(match.groups()[4:])
        if start < previous_end or end <= start:
            raise RuntimeError("existing full VTT contains overlapping or invalid cues")
        ranges.append((start, end))
        previous_end = end
    if not ranges:
        raise RuntimeError("existing full VTT contains no cues")
    return ranges


def candidate_entry(video_id: str) -> dict[str, Any]:
    raw = load_json(ROOT / "data" / "highlight-candidates.json")
    if not isinstance(raw, list):
        raise RuntimeError("highlight candidate queue is invalid")
    for entry in raw:
        if isinstance(entry, dict) and entry.get("youtubeId") == video_id:
            if entry.get("suggestedSourceWorkflow") != "existing-full-subtitles":
                raise RuntimeError("candidate is not an existing-full-subtitles job")
            return entry
    raise RuntimeError("video is not present in the durable highlight candidate queue")


def validate_scenes(
    raw: Any, cue_ranges: list[tuple[float, float]], clusters: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("highlight-scenes.json must be a non-empty list")
    scenes: list[dict[str, Any]] = []
    previous_end = -1
    for index, scene in enumerate(raw, start=1):
        if not isinstance(scene, dict) or set(scene) != {"startSeconds", "endSeconds", "title"}:
            raise RuntimeError(f"scene {index} has an invalid schema")
        start, end, title = scene["startSeconds"], scene["endSeconds"], scene["title"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or start < previous_end
        ):
            raise RuntimeError(f"scene {index} has invalid or overlapping boundaries")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise RuntimeError(f"scene {index} has an invalid title")
        contained = [(cue_start, cue_end) for cue_start, cue_end in cue_ranges if start <= cue_start < end]
        if not contained or contained[0][0] != start:
            raise RuntimeError(f"scene {index} must begin on an existing VTT cue")
        if any(cue_end > end for _, cue_end in contained):
            raise RuntimeError(f"an existing VTT cue crosses scene {index}'s end")
        scenes.append({"startSeconds": start, "endSeconds": end, "title": title.strip()})
        previous_end = end

    peaks = []
    for cluster in clusters:
        peak = cluster.get("peakSeconds") if isinstance(cluster, dict) else None
        if isinstance(peak, bool) or not isinstance(peak, (int, float)):
            raise RuntimeError("candidate queue contains an invalid heatmap cluster")
        peaks.append(peak)
    uncovered = [
        peak
        for peak in peaks
        if not any(scene["startSeconds"] <= peak < scene["endSeconds"] for scene in scenes)
    ]
    if uncovered:
        raise RuntimeError(f"highlight scenes do not preserve heatmap peak(s): {uncovered}")
    return scenes


def validate_review(path: Path, video_id: str, scenes: list[dict[str, Any]], clusters: list[dict[str, Any]]) -> None:
    review = load_json(path)
    if not isinstance(review, dict) or review.get("youtubeId") != video_id:
        raise RuntimeError("highlight-review.json is missing or mismatched")
    if review.get("method") != "existing-full-subtitles":
        raise RuntimeError("highlight review method is invalid")
    if review.get("semanticAuthority") != "korean-source-cues":
        raise RuntimeError("Korean source cues must be the semantic authority")
    passes = review.get("reviewPasses")
    if not isinstance(passes, list) or len(passes) != 2 or any(
        not isinstance(item, dict) or item.get("pass") != index or item.get("completed") is not True
        for index, item in enumerate(passes, start=1)
    ):
        raise RuntimeError("exactly two completed context-review passes are required")
    assignments = review.get("clusterAssignments")
    expected = sorted(float(cluster["peakSeconds"]) for cluster in clusters)
    observed = sorted(
        float(item.get("peakSeconds"))
        for item in assignments
        if isinstance(item, dict) and isinstance(item.get("peakSeconds"), (int, float))
    ) if isinstance(assignments, list) else []
    if observed != expected:
        raise RuntimeError("review must explicitly assign every saved heatmap peak")
    starts = {scene["startSeconds"] for scene in scenes}
    if any(item.get("sceneStartSeconds") not in starts for item in assignments):
        raise RuntimeError("review assigns a heatmap peak to an unknown scene")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")

    work = WORK_ROOT / args.video_id
    scene_path = work / "highlight-scenes.json"
    review_path = work / "highlight-review.json"
    source_path = work / "source-cues.json"
    vtt_path = ROOT / "subtitles" / f"{args.video_id}.vtt"
    metadata_path = ROOT / "metadata" / f"{args.video_id}.json"
    for path in (scene_path, review_path, source_path, vtt_path, metadata_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"required non-empty file is missing: {path}")

    candidate = candidate_entry(args.video_id)
    clusters = candidate.get("hotClusters")
    if not isinstance(clusters, list) or not clusters:
        raise RuntimeError("candidate has no preserved heatmap clusters")
    scenes = validate_scenes(load_json(scene_path), parse_vtt_ranges(vtt_path), clusters)
    validate_review(review_path, args.video_id, scenes, clusters)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    seal = {
        "version": 1,
        "youtubeId": args.video_id,
        "mode": "existing-full-highlights",
        "validatedAt": now,
        "publicationApproved": False,
        "sceneCount": len(scenes),
        "preservedHeatmapPeakCount": len(clusters),
        "files": {
            path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
            for path in (scene_path, review_path)
        },
        "dependencies": {
            f"subtitles/{args.video_id}.vtt": {"sha256": digest(vtt_path), "bytes": vtt_path.stat().st_size},
            f"metadata/{args.video_id}.json": {"sha256": digest(metadata_path), "bytes": metadata_path.stat().st_size},
            "source-cues.json": {"sha256": digest(source_path), "bytes": source_path.stat().st_size},
        },
    }
    atomic_write_json(work / "highlight-approval-ready.json", seal)
    atomic_write_json(
        work / "highlight-selection-state.json",
        {
            "version": 1,
            "youtubeId": args.video_id,
            "status": "ready_for_publication_approval",
            "validatedAt": now,
            "publicationApproved": False,
            "nextAction": "Wait for the user's separate publication approval.",
        },
    )
    print(
        f"PASS: {len(scenes)} reviewed scene(s) preserve all {len(clusters)} saved heatmap peak(s); "
        "the existing full VTT is unchanged."
    )
    print(f"SEALED: {args.video_id} highlight selection is ready for publication approval.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
