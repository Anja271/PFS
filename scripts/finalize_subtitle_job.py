#!/usr/bin/env python3
"""Run every local gate and seal a subtitle job for later publication approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_metadata(path: Path, video_id: str) -> None:
    metadata = load_json(path)
    if not isinstance(metadata, dict) or set(metadata) != {
        "youtubeId",
        "date",
        "originalTitle",
        "displayTitle",
    }:
        raise RuntimeError("publish-metadata.json must use exactly the four required fields")
    if metadata["youtubeId"] != video_id:
        raise RuntimeError("publish metadata video ID does not match the job")
    if metadata["date"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata["date"]):
        raise RuntimeError("publish metadata date must be empty or YYYY-MM-DD")
    for key in ("originalTitle", "displayTitle"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise RuntimeError(f"publish metadata {key} must be non-empty text")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")
    work = WORK_ROOT / args.video_id
    state_path = work / "job-state.json"
    state = load_json(state_path)
    if not isinstance(state, dict) or state.get("youtubeId") != args.video_id:
        raise RuntimeError("missing or mismatched prepared job state")
    mode = state.get("mode")
    if mode not in {"full", "highlights"}:
        raise RuntimeError("job mode must be full or highlights")

    candidate = work / "candidate.vtt"
    source = work / "source-cues.json"
    boundary_file = work / ("chapters.json" if mode == "full" else "scenes.json")
    review = work / "review.md"
    metadata = work / "publish-metadata.json"
    for path in (candidate, source, boundary_file, review, metadata):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"required non-empty job file is missing: {path.name}")
    validate_metadata(metadata, args.video_id)
    validator = ROOT / "tools" / (
        "validate_subtitle_package.py" if mode == "full" else "validate_partial_subtitle_package.py"
    )
    command = [sys.executable, str(validator), "--source", str(source), "--vtt", str(candidate)]
    command += ["--chapters" if mode == "full" else "--scenes", str(boundary_file)]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode:
        raise RuntimeError(f"subtitle validation failed:\n{output}")

    files = [candidate, boundary_file, review, metadata]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    seal = {
        "version": 1,
        "youtubeId": args.video_id,
        "mode": mode,
        "validatedAt": now,
        "validatorResult": output,
        "publicationApproved": False,
        "files": {path.name: {"sha256": digest(path), "bytes": path.stat().st_size} for path in files},
    }
    write_json(work / "approval-ready.json", seal)
    state.update(
        {
            "status": "ready_for_publication_approval",
            "validatedAt": now,
            "publicationApproved": False,
            "nextAction": "Wait for the user's separate publication approval.",
        }
    )
    write_json(state_path, state)
    print(output)
    print(f"SEALED: {args.video_id} is ready for a separate publication approval; nothing was published.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
