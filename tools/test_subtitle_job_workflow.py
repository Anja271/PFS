#!/usr/bin/env python3
"""Dependency-light structural checks for the two-gate subtitle workflow."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_preparer():
    path = ROOT / "scripts" / "prepare_stream.py"
    spec = importlib.util.spec_from_file_location("prepare_stream", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load prepare_stream.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    for relative in (
        "scripts/prepare_stream.py",
        "scripts/finalize_subtitle_job.py",
        "scripts/finalize_vlast_caption_job.py",
        "scripts/publish_subtitle_job.py",
    ):
        ast.parse((ROOT / relative).read_text(encoding="utf-8"))

    preparer = load_preparer()
    known = [{"youtubeId": "known123"}]
    assert preparer.parse_target("latest", known) == ["known123"]
    assert preparer.parse_target("new456XYZ", known) == ["new456XYZ"]
    assert preparer.parse_target(
        "https://www.youtube.com/live/2Y-McTC9PBg?si=test", known
    ) == ["2Y-McTC9PBg"]
    cues = preparer.source_cues(
        {
            "events": [
                {"tStartMs": 1001, "segs": [{"utf8": "첫째"}]},
                {"tStartMs": 1900, "segs": [{"utf8": "둘째"}]},
                {"tStartMs": 4100, "segs": [{"utf8": "셋째"}]},
            ]
        }
    )
    assert [cue["startSeconds"] for cue in cues] == [1, 4]
    assert cues[0]["sourceParts"] == ["첫째", "둘째"]

    points = [
        {"startSeconds": 100.0, "endSeconds": 110.0, "value": 0.8},
        {"startSeconds": 120.0, "endSeconds": 130.0, "value": 0.7},
        {"startSeconds": 900.0, "endSeconds": 910.0, "value": 0.9},
    ]
    source = [
        {"startSeconds": second}
        for second in range(0, 1101)
    ]
    plan = preparer.scene_plan(points, source)
    assert len(plan) == 2
    assert all(scene["parallelEligible"] is False for scene in plan)
    assert all(scene["independenceStatus"] == "requires-context-review" for scene in plan)
    assert all("discovery input" in scene["note"] for scene in plan)

    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        progress_path = preparer.initialize_translation_progress(
            work, "abc123XYZ", "full", 3, "2026-08-08T00:00:00Z"
        )
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        assert progress_path.name == "translation-progress.json"
        assert progress["youtubeId"] == "abc123XYZ"
        assert progress["sourceCueCount"] == 3
        progress["cues"].append([1, "Translated cue"])
        progress_path.write_text(json.dumps(progress), encoding="utf-8")
        preparer.initialize_translation_progress(
            work, "abc123XYZ", "full", 3, "2026-08-08T00:01:00Z"
        )
        resumed = json.loads(progress_path.read_text(encoding="utf-8"))
        assert resumed["cues"] == [[1, "Translated cue"]]
        assert list(work.glob("progress-*.json")) == []

        finalizer = load_module(
            "scripts/finalize_subtitle_job.py", "finalize_subtitle_job_progress_test"
        )
        state = {"translationProgressFile": "translation-progress.json"}
        finalizer.validate_single_translation_progress(work, state, "abc123XYZ")
        (work / "progress-001.json").write_text("{}", encoding="utf-8")
        try:
            finalizer.validate_single_translation_progress(work, state, "abc123XYZ")
        except RuntimeError as error:
            assert "forbidden" in str(error)
        else:
            raise AssertionError("numbered progress files must block finalization")
        (work / "progress-001.json").unlink()
        (work / "scene-1-translation.json").write_text("{}", encoding="utf-8")
        try:
            finalizer.validate_single_translation_progress(work, state, "abc123XYZ")
        except RuntimeError as error:
            assert "forbidden" in str(error)
        else:
            raise AssertionError("per-scene progress files must block finalization")

    with tempfile.TemporaryDirectory() as directory:
        assisted = Path(directory)
        video_id = "abc123XYZ"
        overrides = [{"startMs": 1000, "replacement": "YJ: Revised"}]
        fixtures = {
            "translation-progress.json": {
                "youtubeId": video_id,
                "status": "review-complete",
                "reviewSamples": overrides,
                "uncertainties": [],
            },
            "quality-audit.json": {
                "youtubeId": video_id,
                "pendingIssueCount": 0,
                "reviewChunks": [
                    {"status": "reviewed", "reviewPasses": 2},
                    {"status": "reviewed", "reviewPasses": 2},
                ],
            },
            "pilot-report.json": {
                "youtubeId": video_id,
                "pilotCueCount": 2,
                "appliedKoreanLedEditorialOverrides": 1,
                "replacedLyricEvents": 1,
            },
            "pilot-metadata.json": {
                "youtubeId": video_id,
                "mediaDownloaded": False,
                "publicationApproved": False,
            },
            "editorial-overrides.json": overrides,
            "confirmed-song-ranges.json": [{"startMs": 1000, "endMs": 2000}],
        }
        for name, value in fixtures.items():
            (assisted / name).write_text(json.dumps(value), encoding="utf-8")
        assisted_finalizer = load_module(
            "scripts/finalize_vlast_caption_job.py", "finalize_vlast_caption_job_test"
        )
        summary = assisted_finalizer.validate_review_state(assisted, video_id)
        assert summary["reviewedContextChunks"] == 2
        assert summary["editorialOverrideCount"] == 1
        fixtures["quality-audit.json"]["reviewChunks"][0]["reviewPasses"] = 1
        (assisted / "quality-audit.json").write_text(
            json.dumps(fixtures["quality-audit.json"]), encoding="utf-8"
        )
        try:
            assisted_finalizer.validate_review_state(assisted, video_id)
        except RuntimeError as error:
            assert "two completed review passes" in str(error)
        else:
            raise AssertionError("a one-pass assisted review must not be sealable")

        candidate = assisted / "candidate.vtt"
        candidate.write_text(
            "WEBVTT\n\n00:00:01.250 --> 00:00:02.000\nYejun: First\n\n"
            "00:00:03.500 --> 00:00:04.000\nNoah: Second\n",
            encoding="utf-8",
        )
        chapters = assisted / "chapters.json"
        chapters.write_text(
            json.dumps(
                [
                    {"startSeconds": 1, "title": "Opening"},
                    {"startSeconds": 3, "title": "Conversation"},
                ]
            ),
            encoding="utf-8",
        )
        assert len(assisted_finalizer.validate_chapters(chapters, candidate)) == 2

    update_path = ROOT / "scripts" / "update_videos.py"
    update_tree = ast.parse(update_path.read_text(encoding="utf-8"))
    top_level_imports = [
        node
        for node in update_tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not any(
        (isinstance(node, ast.ImportFrom) and node.module == "yt_dlp")
        or (
            isinstance(node, ast.Import)
            and any(alias.name == "yt_dlp" for alias in node.names)
        )
        for node in top_level_imports
    )
    update_module = load_module("scripts/update_videos.py", "update_videos_dependency_test")
    assert callable(update_module.update_subtitle_manifest)

    publish_source = (ROOT / "scripts" / "publish_subtitle_job.py").read_text(encoding="utf-8")
    assert "merge_prepared_heatmap(work, args.video_id)" in publish_source
    assert '"data/heatmaps.json"' in publish_source
    assert "synchronize_clean_main()" in publish_source
    assert publish_source.index("synchronize_clean_main()") < publish_source.index(
        "for source, destination in destinations.items():"
    )
    assert "snapshot_files(mutable_paths)" in publish_source
    assert "restore_files(snapshot)" in publish_source
    publish_module = load_module(
        "scripts/publish_subtitle_job.py", "publish_subtitle_job_heatmap_test"
    )
    with tempfile.TemporaryDirectory() as directory:
        # Assisted jobs do not have a replay heatmap; that is a valid no-op.
        publish_module.merge_prepared_heatmap(Path(directory), "abc123XYZ")
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        source = temporary / "scenes.json"
        destination = temporary / "published.json"
        source.write_text(
            json.dumps([{"startSeconds": 10, "endSeconds": 20, "title": "Scene"}]),
            encoding="utf-8",
        )
        publish_module.publish_highlight_boundaries(source, destination)
        published = json.loads(destination.read_text(encoding="utf-8"))
        assert published == [{
            "startSeconds": 10,
            "endSeconds": 20,
            "title": "Scene",
            "legendary": False,
            "everMostReplayed": True,
        }]

    tools_path = str(ROOT / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    validator = load_module(
        "tools/validate_subtitle_package.py", "validate_subtitle_package_density_test"
    )
    warnings = validator.readability_warnings(
        [{"start": 0, "end": 999, "text": "x" * 43}]
    )
    assert len(warnings) == 1
    assert validator.readability_warnings(
        [{"start": 0, "end": 999, "text": "short text"}]
    ) == []
    validator.validate_standalone_ja(
        [{"text": "Ja, ja... Next topic."}],
        [{"source": "자, 자, 다음 주제"}],
    )
    try:
        validator.validate_standalone_ja(
            [{"text": "All right. Next topic."}],
            [{"source": "자, 다음 주제"}],
        )
    except ValueError as error:
        assert "자/ja count differs" in str(error)
    else:
        raise AssertionError("standalone 자 must survive as romanized ja")
    validator.validate_duduhanda(
        [{"text": "I'll dudu--the tone makes the meaning clear."}],
        [{"source": "나 두두할 거야"}],
    )
    try:
        validator.validate_duduhanda(
            [{"text": "I'll do it."}],
            [{"source": "나 두두할 거야"}],
        )
    except ValueError as error:
        assert "duduhanda form" in str(error)
    else:
        raise AssertionError("duduhanda conjugations must retain visible dudu")
    validator.validate_bong_catchphrase(
        [{"text": "Bongus--Bonggu's hosting catchphrase."}],
        [{"source": "벙커스"}],
    )
    try:
        validator.validate_bong_catchphrase(
            [{"text": "All right, next topic."}],
            [{"source": "벙커스"}],
        )
    except ValueError as error:
        assert "catchphrase reference" in str(error)
    else:
        raise AssertionError("Bonguk/Bongus callbacks must remain visible")
    validator.validate_hamin_wordplay(
        [
            {"text": "Geuman-Hamin..."},
            {"text": "What are you saying?"},
            {"text": '"Geuman-Hamin." Then, "geuman-min."'},
        ],
        [
            {"source": "그만 하면"},
            {"source": "뭐라는 거야?"},
            {"source": "그만하민 그만민"},
        ],
    )
    try:
        validator.validate_hamin_wordplay(
            [
                {"text": "Stop it..."},
                {"text": "What are you saying?"},
                {"text": "Stop it."},
            ],
            [
                {"source": "그만 하면"},
                {"source": "뭐라는 거야?"},
                {"source": "그만하민 그만민"},
            ],
        )
    except ValueError as error:
        assert "-Hamin/-min wordplay" in str(error)
    else:
        raise AssertionError("the split-ASR first Geuman-Hamin coinage must remain visible")
    print(
        "PASS: two-gate scripts parse; cue merging, semantic scene planning, "
        "single-file resumable progress, two-pass assisted sealing, dependency-light publication, remote preflight, "
        "rollback, density warnings, standalone ja preservation, duduhanda retention, "
        "Bong catchphrase preservation, and Hamin-wordplay retention work."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
