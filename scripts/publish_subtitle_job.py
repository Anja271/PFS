#!/usr/bin/env python3
"""Publish one sealed subtitle job after a separate explicit approval.

This command copies only the sealed package, rebuilds static manifests, commits
only its allow-listed paths, and pushes main. Never call it during translation.
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


def run(command: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=capture, check=False
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        raise RuntimeError(detail)
    return completed.stdout.strip() if capture else ""


def command_succeeds(command: list[str]) -> bool:
    return subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    ).returncode == 0


def synchronize_clean_main() -> None:
    """Fast-forward a clean local main before any publication files change."""

    run(["git", "fetch", "origin", "main"])
    local = run(["git", "rev-parse", "HEAD"], capture=True)
    remote = run(["git", "rev-parse", "origin/main"], capture=True)
    if local == remote:
        return
    if command_succeeds(["git", "merge-base", "--is-ancestor", local, remote]):
        run(["git", "merge", "--ff-only", "origin/main"])
        return
    raise RuntimeError(
        "local main is ahead of or diverged from origin/main; refusing to publish unrelated commits"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_files(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.is_file() else None for path in paths}


def restore_files(snapshot: dict[Path, bytes | None]) -> None:
    for path, payload in snapshot.items():
        if payload is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(path, payload)


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def merge_prepared_heatmap(work: Path, video_id: str) -> None:
    prepared = load_json(work / "heatmap.json")
    if not isinstance(prepared, list) or not prepared:
        return
    manifest_path = ROOT / "data" / "heatmaps.json"
    try:
        manifest = load_json(manifest_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        manifest = {}
    if not isinstance(manifest, dict):
        raise RuntimeError("data/heatmaps.json is not a valid object")
    manifest[video_id] = prepared
    atomic_write_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    parser.add_argument(
        "--confirm-publication",
        action="store_true",
        help="required acknowledgement that this is the separate publication gate",
    )
    args = parser.parse_args()
    if not args.confirm_publication:
        raise RuntimeError("publication requires --confirm-publication")
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")
    if run(["git", "branch", "--show-current"], capture=True) != "main":
        raise RuntimeError("publication is allowed only from main")
    tracked_changes = run(["git", "status", "--porcelain", "--untracked-files=no"], capture=True)
    if tracked_changes:
        raise RuntimeError("tracked repository changes exist; review or commit them before publication")
    synchronize_clean_main()

    work = WORK_ROOT / args.video_id
    seal = load_json(work / "approval-ready.json")
    if not isinstance(seal, dict) or seal.get("youtubeId") != args.video_id:
        raise RuntimeError("no matching sealed approval-ready package exists")
    if seal.get("publicationApproved") is not False:
        raise RuntimeError("sealed package has an invalid publication state")
    mode = seal.get("mode")
    if mode not in {"full", "highlights"}:
        raise RuntimeError("sealed package mode is invalid")
    for name, descriptor in seal.get("files", {}).items():
        path = work / name
        if not path.is_file() or not isinstance(descriptor, dict) or sha256(path) != descriptor.get("sha256"):
            raise RuntimeError(f"sealed file changed after validation: {name}")

    candidate = work / "candidate.vtt"
    boundary = work / ("chapters.json" if mode == "full" else "scenes.json")
    metadata = work / "publish-metadata.json"
    if mode == "full":
        destinations = {
            candidate: ROOT / "subtitles" / f"{args.video_id}.vtt",
            boundary: ROOT / "chapters" / f"{args.video_id}.json",
        }
    else:
        destinations = {
            candidate: ROOT / "highlight-subtitles" / f"{args.video_id}.vtt",
            boundary: ROOT / "highlights" / f"{args.video_id}.json",
        }
    destinations[metadata] = ROOT / "metadata" / f"{args.video_id}.json"
    # Import every publication dependency before changing public files. The
    # manifest helpers are intentionally dependency-light, so this preflight
    # does not require yt-dlp or network access.
    sys.path.insert(0, str(ROOT / "scripts"))
    from update_highlights import main as update_highlights  # pylint: disable=import-outside-toplevel
    from update_videos import update_chapter_manifest, update_subtitle_manifest  # pylint: disable=import-outside-toplevel

    public_paths = [str(path.relative_to(ROOT)) for path in destinations.values()]
    generated_paths = [
        "data/subtitles.json",
        "data/chapters.json",
        "data/subtitle-coverage.json",
        "data/highlights.json",
        "data/heatmaps.json",
    ]
    mutable_paths = list(destinations.values()) + [ROOT / path for path in generated_paths]
    snapshot = snapshot_files(mutable_paths)
    committed = False
    try:
        for source, destination in destinations.items():
            atomic_copy(source, destination)
        merge_prepared_heatmap(work, args.video_id)
        update_subtitle_manifest()
        update_chapter_manifest()
        update_highlights()

        run(["git", "add", "--", *public_paths, *generated_paths])
        staged = run(["git", "diff", "--cached", "--name-only"], capture=True).splitlines()
        allowed = set(public_paths + generated_paths)
        if not staged:
            raise RuntimeError("publication produced no changes")
        if any(path not in allowed for path in staged):
            raise RuntimeError("staging contains a path outside the publication allow-list")
        label = "English fan subtitles" if mode == "full" else "English fan-subtitled highlights"
        run(["git", "commit", "-m", f"Add {label} for {args.video_id}"])
        committed = True
        run(["git", "push", "origin", "main"])
    except Exception:
        if not committed:
            subprocess.run(
                ["git", "restore", "--staged", "--", *public_paths, *generated_paths],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            restore_files(snapshot)
        raise

    state_path = work / "job-state.json"
    state = load_json(state_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state.update(
        {
            "status": "published",
            "publishedAt": now,
            "publishedCommit": run(["git", "rev-parse", "HEAD"], capture=True),
            "publicationApproved": True,
            "nextAction": (
                "Confirm the update workflow and the newest successor Pages deployment; "
                "an earlier Pages run may be cancelled when the update workflow pushes a follow-up commit."
            ),
        }
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PUBLISHED: {args.video_id} was committed and pushed to main.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
