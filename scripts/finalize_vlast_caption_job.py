#!/usr/bin/env python3
"""Validate and seal a completed VLAST-assisted subtitle job.

This is the approval-gate-2 boundary for the assisted workflow.  It promotes
only the already reviewed local candidate into the standard publication
package; it never edits public files, commits, pushes, or deploys anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
TIMING_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})$"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cue_start_seconds(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("WEBVTT\n\n"):
        raise RuntimeError("candidate VTT has an invalid header")
    starts: list[int] = []
    for block in text.rstrip("\n").split("\n\n")[1:]:
        timing = block.splitlines()[0] if block.splitlines() else ""
        match = TIMING_RE.fullmatch(timing)
        if not match:
            raise RuntimeError("candidate VTT contains a malformed timing line")
        hours, minutes, seconds, millis = map(int, match.groups()[:4])
        starts.append(((hours * 60 + minutes) * 60 + seconds) * 1000 + millis)
    if not starts:
        raise RuntimeError("candidate VTT contains no cues")
    return [value // 1000 for value in starts]


def validate_chapters(path: Path, candidate: Path) -> list[dict[str, Any]]:
    chapters = load_json(path)
    if not isinstance(chapters, list) or not chapters:
        raise RuntimeError("chapters.json must be a non-empty list")
    cue_seconds = set(cue_start_seconds(candidate))
    previous = -1
    for number, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict) or set(chapter) != {"startSeconds", "title"}:
            raise RuntimeError(f"chapter {number} must use exactly startSeconds and title")
        start = chapter["startSeconds"]
        title = chapter["title"]
        if isinstance(start, bool) or not isinstance(start, int) or start <= previous:
            raise RuntimeError(f"chapter {number} startSeconds is invalid or non-increasing")
        if start not in cue_seconds:
            raise RuntimeError(f"chapter {number} does not match a candidate cue start")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise RuntimeError(f"chapter {number} title is invalid")
        if "<" in title or ">" in title or "♪" in title:
            raise RuntimeError(f"chapter {number} title contains forbidden markup")
        previous = start
    if chapters[0]["startSeconds"] != min(cue_seconds):
        raise RuntimeError("the first chapter must match the first candidate cue")
    return chapters


def validate_metadata(path: Path, video_id: str) -> dict[str, str]:
    metadata = load_json(path)
    required = {"youtubeId", "date", "originalTitle", "displayTitle"}
    if not isinstance(metadata, dict) or set(metadata) != required:
        raise RuntimeError("publish-metadata.json must use exactly the four required fields")
    if metadata.get("youtubeId") != video_id:
        raise RuntimeError("publish metadata video ID does not match the job")
    if metadata.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata["date"]):
        raise RuntimeError("publish metadata date must be empty or YYYY-MM-DD")
    for key in ("originalTitle", "displayTitle"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise RuntimeError(f"publish metadata {key} must be non-empty text")
    return metadata


def validate_review_state(work: Path, video_id: str) -> dict[str, Any]:
    progress = load_json(work / "translation-progress.json")
    audit = load_json(work / "quality-audit.json")
    report = load_json(work / "pilot-report.json")
    metadata = load_json(work / "pilot-metadata.json")
    overrides = load_json(work / "editorial-overrides.json")
    songs = load_json(work / "confirmed-song-ranges.json")
    for value, label in ((progress, "progress"), (audit, "audit"), (report, "report"), (metadata, "metadata")):
        if not isinstance(value, dict) or value.get("youtubeId") != video_id:
            raise RuntimeError(f"assisted {label} belongs to another video")
    if progress.get("status") != "review-complete":
        raise RuntimeError("full contextual review is not complete")
    if audit.get("pendingIssueCount") != 0:
        raise RuntimeError("quality audit still contains pending items")
    chunks = audit.get("reviewChunks")
    if not isinstance(chunks, list) or not chunks or any(
        chunk.get("status") != "reviewed" or chunk.get("reviewPasses", 0) < 2
        for chunk in chunks
    ):
        raise RuntimeError("every context chunk must have two completed review passes")
    if not isinstance(overrides, list) or progress.get("reviewSamples") != overrides:
        raise RuntimeError("the single progress ledger does not match editorial overrides")
    if report.get("appliedKoreanLedEditorialOverrides") != len(overrides):
        raise RuntimeError("the candidate report does not match editorial overrides")
    if not isinstance(songs, list) or not songs or report.get("replacedLyricEvents", 0) <= 0:
        raise RuntimeError("confirmed song ranges were not safely handled")
    if progress.get("uncertainties"):
        raise RuntimeError("speaker or semantic uncertainties remain unresolved")
    if metadata.get("mediaDownloaded") is not False or metadata.get("publicationApproved") is not False:
        raise RuntimeError("pilot metadata has an invalid source or approval state")
    return {
        "reviewedContextChunks": len(chunks),
        "editorialOverrideCount": len(overrides),
        "confirmedSongRangeCount": len(songs),
        "candidateCueCount": report.get("pilotCueCount"),
    }


def run_assisted_validator(video_id: str) -> str:
    command = [
        sys.executable,
        str(ROOT / "tools" / "validate_vlast_caption_pilot.py"),
        video_id,
        "--require-reviewed",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode:
        raise RuntimeError(f"assisted subtitle validation failed:\n{output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")

    root_work = WORK_ROOT / args.video_id
    assisted = root_work / "vlast-assisted"
    candidate = assisted / "candidate.diagnostic.vtt"
    chapters = assisted / "chapters.json"
    review = assisted / "review.md"
    metadata = assisted / "publish-metadata.json"
    provenance_names = [
        "pilot-metadata.json",
        "pilot-report.json",
        "translation-progress.json",
        "quality-audit.json",
        "editorial-overrides.json",
        "confirmed-song-ranges.json",
    ]
    required = [candidate, chapters, review, metadata] + [assisted / name for name in provenance_names]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"required non-empty assisted file is missing: {path.name}")

    review_summary = validate_review_state(assisted, args.video_id)
    validate_metadata(metadata, args.video_id)
    validate_chapters(chapters, candidate)
    validator_output = run_assisted_validator(args.video_id)

    promoted = {
        candidate: root_work / "candidate.vtt",
        chapters: root_work / "chapters.json",
        review: root_work / "review.md",
        metadata: root_work / "publish-metadata.json",
    }
    for source, destination in promoted.items():
        atomic_copy(source, destination)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state = {
        "version": 1,
        "youtubeId": args.video_id,
        "mode": "full",
        "workflow": "vlast-assisted",
        "status": "ready_for_publication_approval",
        "translationProgressFile": "vlast-assisted/translation-progress.json",
        "validatedAt": now,
        "publicationApproved": False,
        "nextAction": "Wait for the user's separate publication approval.",
    }
    seal_files = list(promoted.values())
    seal = {
        "version": 2,
        "youtubeId": args.video_id,
        "mode": "full",
        "workflow": "vlast-assisted",
        "validatedAt": now,
        "validatorResult": validator_output,
        "reviewSummary": review_summary,
        "publicationApproved": False,
        "files": {
            path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
            for path in seal_files
        },
        "provenance": {
            f"vlast-assisted/{name}": {
                "sha256": digest(assisted / name),
                "bytes": (assisted / name).stat().st_size,
            }
            for name in provenance_names
        },
    }
    atomic_write_json(root_work / "job-state.json", state)
    atomic_write_json(root_work / "approval-ready.json", seal)
    print(validator_output)
    print(
        f"SEALED: {args.video_id} VLAST-assisted candidate is ready for a separate "
        "publication approval; nothing was published."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
