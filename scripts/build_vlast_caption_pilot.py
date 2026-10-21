#!/usr/bin/env python3
"""Build a non-publishable readability pilot from prepared VLAST captions."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import tempfile
import textwrap
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
SPEAKER_RE = re.compile(r"^(YJ|NA|BB|EH|HM):\s*(.*)$", re.DOTALL)
KOREAN_SPEAKER_RE = re.compile(r"^(예준|노아|밤비|은호|하민):\s*(.*)$", re.DOTALL)
SPEAKER_NAMES = {
    "YJ": "Yejun",
    "NA": "Noah",
    "BB": "Bamby",
    "EH": "Eunho",
    "HM": "Hamin",
}
KOREAN_TO_CODE = {
    "예준": "YJ",
    "노아": "NA",
    "밤비": "BB",
    "은호": "EH",
    "하민": "HM",
}
KOREAN_PREFIX_RE = re.compile(r"^(?:예준|노아|밤비|은호|하민):\s*")
STANDALONE_JA_RE = re.compile(r"(?<![가-힣])자(?![가-힣])")
REACTION_RE = re.compile(
    r"^(?:ah+|oh+|oh my gosh|wow+|yeah+|yes|yep|right|okay|ok|great|nice|"
    r"huh|what|really|no way|exactly|mm+|hmm+|thank you|congratulations|"
    r"let's go|that's right|good)(?:[.!?, ]*)$",
    re.IGNORECASE,
)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read valid JSON: {path}") from error


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def speaker_and_body(text: str) -> tuple[str | None, str]:
    match = SPEAKER_RE.match(text.strip())
    return (match.group(1), match.group(2).strip()) if match else (None, text.strip())


def korean_speaker(text: str) -> str | None:
    match = KOREAN_SPEAKER_RE.match(text.strip())
    return KOREAN_TO_CODE.get(match.group(1)) if match else None


def is_fragment(text: str) -> bool:
    body = text.rstrip()
    return bool(body) and (body.endswith("...") or body[-1] not in ".!?…)]\"'")


def overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["startMs"] < right["endMs"] and right["startMs"] < left["endMs"]


def as_cues(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for event in events:
        speaker, body = speaker_and_body(str(event.get("text") or ""))
        if not body:
            continue
        start = int(event["startMs"])
        duration = max(200, int(event.get("durationMs") or 0))
        cues.append(
            {
                "startMs": start,
                "endMs": start + duration,
                "originalEndMs": start + duration,
                "speaker": speaker,
                "body": body,
                "sourceIndexes": [len(cues)],
            }
        )
    return sorted(cues, key=lambda cue: (cue["startMs"], cue["endMs"]))


def apply_editorial_overrides(
    events: list[dict[str, Any]], overrides: list[dict[str, Any]]
) -> int:
    by_start: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        by_start.setdefault(int(event["startMs"]), []).append(event)
    applied = 0
    for override in overrides:
        start = int(override["startMs"])
        candidates = by_start.get(start) or []
        if not candidates:
            raise RuntimeError(f"editorial override has no English source event at {start}ms")
        expected = str(override["expectedSource"])
        matches = [
            event for event in candidates if str(event.get("text") or "") == expected
        ]
        if len(matches) != 1:
            raise RuntimeError(f"editorial override source changed at {start}ms")
        event = matches[0]
        replacement = str(override["replacement"]).strip()
        if not replacement:
            raise RuntimeError(f"editorial override is empty at {start}ms")
        event["text"] = replacement
        # A speaker-only replacement is an explicit editorial suppression.
        # Do not let later source policies resurrect it as a standalone
        # discourse marker (for example, ``EH:`` becoming ``EH: ja``).
        _, replacement_body = speaker_and_body(replacement)
        event["editoriallySuppressed"] = not replacement_body
        event["disableJaRestoration"] = bool(override.get("disableJaRestoration"))
        applied += 1
    return applied


def source_ja_count(text: str) -> int:
    body = KOREAN_PREFIX_RE.sub("", text, count=1)
    count = len(STANDALONE_JA_RE.findall(body))
    leading = re.match(r"^(자{2,})(?![가-힣])", body)
    if leading:
        count += len(leading.group(1))
    return count


def korean_text_for_source_span(start: int, end: int, korean: list[dict[str, Any]]) -> str:
    related: list[str] = []
    for candidate in korean:
        candidate_start = int(candidate["startMs"])
        if start <= candidate_start < end:
            related.append(str(candidate.get("text") or ""))
        if candidate_start >= end:
            break
    return " | ".join(related)


def apply_safe_source_policies(
    english: list[dict[str, Any]],
    korean: list[dict[str, Any]],
    song_ranges: list[dict[str, Any]],
) -> dict[str, int]:
    ja_restored = 0
    lyric_events_replaced = 0
    for index, event in enumerate(english):
        if event.get("editoriallySuppressed"):
            continue
        start = int(event["startMs"])
        next_start = (
            int(english[index + 1]["startMs"])
            if index + 1 < len(english)
            else start + max(300, int(event.get("durationMs") or 0))
        )
        speaker, event_body = speaker_and_body(str(event.get("text") or ""))
        song_range = next(
            (
                item
                for item in song_ranges
                if int(item["startMs"]) <= start < int(item["endMs"])
            ),
            None,
        )
        if song_range is not None:
            description = str(song_range.get("descriptionBySpeaker", {}).get(speaker) or "[Singing]")
            prefix = f"{speaker}: " if speaker else ""
            event["text"] = f"{prefix}{description}"
            lyric_events_replaced += 1
            continue

        korean_text = korean_text_for_source_span(start, next_start, korean)
        expected_ja = sum(source_ja_count(part) for part in korean_text.split(" | "))
        # The joined source normally has no separator, so use the exact Korean
        # regex over the whole aligned span as the stable lower bound.
        expected_ja = max(expected_ja, source_ja_count(korean_text))
        existing_ja = len(re.findall(r"\bja\b", event_body, flags=re.I))
        missing = (
            0
            if event.get("disableJaRestoration")
            else max(0, expected_ja - existing_ja)
        )
        if missing:
            cleaned = re.sub(
                r"^(?:(?:all right|alright|okay|ok|now|so)[,! ]*)+",
                "",
                event_body,
                flags=re.I,
            ).strip()
            marker = ", ".join(["ja"] * missing)
            replacement = f"{marker}, {cleaned}" if cleaned else marker
            prefix = f"{speaker}: " if speaker else ""
            event["text"] = f"{prefix}{replacement}"
            ja_restored += missing
        event["text"] = canonicalize_member_relationships(str(event.get("text") or ""))
    return {
        "restoredStandaloneJaMarkers": ja_restored,
        "replacedLyricEvents": lyric_events_replaced,
    }


def canonicalize_member_relationships(text: str) -> str:
    for name in SPEAKER_NAMES.values():
        text = re.sub(
            rf"\b{re.escape(name)}(?:\s+|-)hyung\b",
            f"{name}-hyung",
            text,
            flags=re.I,
        )
    return text


def suppress_overlapping_reactions(cues: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    suppressed = 0
    for index, cue in enumerate(cues):
        if not REACTION_RE.fullmatch(cue["body"].strip()):
            kept.append(cue)
            continue
        competing = [
            other
            for other_index, other in enumerate(cues)
            if other_index != index
            and other["speaker"] != cue["speaker"]
            and len(other["body"]) > len(cue["body"]) + 12
            and overlaps(cue, other)
        ]
        if competing:
            suppressed += 1
        else:
            kept.append(cue)
    return kept, suppressed


def merge_fragments(cues: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    merged: list[dict[str, Any]] = []
    merge_count = 0
    for cue in cues:
        if not merged:
            merged.append(cue)
            continue
        previous = merged[-1]
        gap = cue["startMs"] - previous["endMs"]
        combined = f"{previous['body']} {cue['body']}".replace("... ...", "...").strip()
        can_merge = (
            cue["speaker"] == previous["speaker"]
            and cue["startMs"] > previous["startMs"]
            and gap <= 450
            and len(combined) <= 110
            and cue["startMs"] - previous["startMs"] <= 6500
            and (is_fragment(previous["body"]) or gap < 0 or gap <= 160)
        )
        if not can_merge:
            merged.append(cue)
            continue
        previous["body"] = combined
        previous["endMs"] = max(previous["endMs"], cue["endMs"])
        previous["originalEndMs"] = max(previous["originalEndMs"], cue["originalEndMs"])
        previous["sourceIndexes"].extend(cue["sourceIndexes"])
        merge_count += 1
    return merged, merge_count


def compose_readable_cards(cues: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Combine tightly timed speech into at most two visible speaker lines."""

    cards: list[dict[str, Any]] = []
    combined_count = 0
    for cue in cues:
        cue_line = format_text(cue)
        if not cards:
            first = dict(cue)
            first["displayLines"] = [cue_line]
            first["lineSpeakers"] = [cue.get("speaker")]
            first["lastStartMs"] = cue["startMs"]
            cards.append(first)
            continue
        card = cards[-1]
        lines = list(card["displayLines"])
        speakers = list(card["lineSpeakers"])
        close_in_time = (
            cue["startMs"] - card["startMs"] <= 4200
            and cue["startMs"] - card["lastStartMs"] <= 1600
        )
        proposed = list(lines)
        if close_in_time and speakers[-1] == cue.get("speaker"):
            body = cue["body"]
            proposed[-1] = f"{proposed[-1]} {body}".replace("... ...", "...").strip()
        elif close_in_time and len(lines) < 2 and len(cue_line) <= 60:
            proposed.append(cue_line)
        else:
            proposed = []
        can_combine = (
            bool(proposed)
            and sum(len(line) for line in proposed) <= 126
            and max(len(line) for line in proposed) <= 76
        )
        if not can_combine:
            new_card = dict(cue)
            new_card["displayLines"] = [cue_line]
            new_card["lineSpeakers"] = [cue.get("speaker")]
            new_card["lastStartMs"] = cue["startMs"]
            cards.append(new_card)
            continue
        card["displayLines"] = proposed
        if len(proposed) > len(lines):
            speakers.append(cue.get("speaker"))
        card["lineSpeakers"] = speakers
        card["lastStartMs"] = cue["startMs"]
        card["endMs"] = max(card["endMs"], cue["endMs"])
        card["originalEndMs"] = max(card["originalEndMs"], cue["originalEndMs"])
        card["sourceIndexes"].extend(cue["sourceIndexes"])
        combined_count += 1
    return cards, combined_count


def group_equal_starts(cues: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    grouped: list[dict[str, Any]] = []
    grouped_count = 0
    for cue in cues:
        if not grouped or cue["startMs"] != grouped[-1]["startMs"]:
            grouped.append(cue)
            continue
        previous = grouped[-1]
        left = format_text(previous)
        right = format_text(cue)
        previous["speaker"] = None
        previous["body"] = f"{left} / {right}"
        previous["endMs"] = max(previous["endMs"], cue["endMs"])
        previous["originalEndMs"] = max(previous["originalEndMs"], cue["originalEndMs"])
        previous["sourceIndexes"].extend(cue["sourceIndexes"])
        grouped_count += 1
    return grouped, grouped_count


def retime(cues: list[dict[str, Any]], video_end_ms: int) -> tuple[list[dict[str, Any]], int]:
    clipped = 0
    for index, cue in enumerate(cues):
        next_start = cues[index + 1]["startMs"] if index + 1 < len(cues) else video_end_ms
        text_length = len(format_text(cue).replace("\n", " "))
        desired_duration = min(6000, max(1400, int(text_length / 17 * 1000)))
        desired_end = max(cue["endMs"], cue["startMs"] + desired_duration)
        safe_end = min(desired_end, next_start - 40, video_end_ms)
        if safe_end != cue["endMs"]:
            clipped += 1
        cue["endMs"] = max(cue["startMs"] + 120, safe_end)
        if cue["endMs"] > next_start and index + 1 < len(cues):
            cue["endMs"] = next_start
    return cues, clipped


def format_text(cue: dict[str, Any]) -> str:
    if isinstance(cue.get("displayLines"), list):
        return "\n".join(str(line) for line in cue["displayLines"])
    speaker = cue.get("speaker")
    prefix = f"{SPEAKER_NAMES[speaker]}: " if speaker in SPEAKER_NAMES else ""
    return f"{prefix}{cue['body']}".strip()


def timestamp(milliseconds: int) -> str:
    total_seconds, millis = divmod(max(0, milliseconds), 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def wrap_text(text: str) -> list[str]:
    if "\n" in text:
        return text.splitlines()
    lines = textwrap.wrap(
        text,
        width=70,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return lines or [text]


def candidate_vtt(cues: list[dict[str, Any]]) -> str:
    blocks = ["WEBVTT", ""]
    for cue in cues:
        blocks.append(f"{timestamp(cue['startMs'])} --> {timestamp(cue['endMs'])}")
        blocks.extend(wrap_text(format_text(cue)))
        blocks.append("")
    return "\n".join(blocks)


def count_overlaps(cues: list[dict[str, Any]]) -> int:
    return sum(
        1
        for index, cue in enumerate(cues[:-1])
        if cue["endMs"] > cues[index + 1]["startMs"]
    )


def align_korean(cues: list[dict[str, Any]], korean: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for cue in cues:
        related = []
        start = cue["startMs"] - 250
        end = cue["originalEndMs"] + 250
        for event in korean:
            event_start = int(event["startMs"])
            event_end = event_start + max(200, int(event.get("durationMs") or 0))
            if event_start < end and start < event_end:
                related.append(event)
            if event_start >= end:
                break
        korean_speakers = sorted(
            {speaker for event in related if (speaker := korean_speaker(str(event.get("text") or "")))}
        )
        english_speaker = cue.get("speaker")
        if english_speaker and korean_speakers and english_speaker not in korean_speakers:
            samples.append(
                {
                    "startMs": cue["startMs"],
                    "english": format_text(cue),
                    "englishSpeaker": english_speaker,
                    "koreanSpeakers": korean_speakers,
                    "korean": [str(event.get("text") or "") for event in related],
                    "reason": "speaker-label-mismatch",
                }
            )
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")
    work = WORK_ROOT / args.video_id / "vlast-assisted"
    metadata = read_json(work / "pilot-metadata.json")
    temporary = Path(str(metadata.get("temporarySourceDirectory") or ""))
    korean = read_json(temporary / "korean-events.json")
    english = read_json(temporary / "english-events.json")
    if not isinstance(korean, list) or not isinstance(english, list):
        raise RuntimeError("prepared caption event files must contain lists")

    overrides_path = work / "editorial-overrides.json"
    overrides = read_json(overrides_path) if overrides_path.exists() else []
    if not isinstance(overrides, list):
        raise RuntimeError("editorial-overrides.json must contain a list")
    applied_overrides = apply_editorial_overrides(english, overrides)
    song_ranges_path = work / "confirmed-song-ranges.json"
    song_ranges = read_json(song_ranges_path) if song_ranges_path.exists() else []
    if not isinstance(song_ranges, list):
        raise RuntimeError("confirmed-song-ranges.json must contain a list")
    policy_counts = apply_safe_source_policies(english, korean, song_ranges)
    original = as_cues(english)
    original_overlaps = count_overlaps(original)
    reduced, suppressed = suppress_overlapping_reactions(original)
    reduced, merged = merge_fragments(reduced)
    reduced, cards_combined = compose_readable_cards(reduced)
    reduced, equal_starts = group_equal_starts(reduced)
    reduced, clipped = retime(reduced, int(metadata["durationSeconds"]) * 1000)
    final_overlaps = count_overlaps(reduced)
    durations = [(cue["endMs"] - cue["startMs"]) / 1000 for cue in reduced]
    fast = [
        cue
        for cue in reduced
        if (cue["endMs"] - cue["startMs"]) < 1000
        or len(format_text(cue)) / max(0.12, (cue["endMs"] - cue["startMs"]) / 1000) > 26
    ]
    mismatches = align_korean(reduced, korean)
    speaker_counts = Counter(cue.get("speaker") or "unknown" for cue in reduced)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report = {
        "version": 1,
        "youtubeId": args.video_id,
        "generatedAt": now,
        "status": "diagnostic-pilot-not-publication-ready",
        "koreanIsAuthoritative": True,
        "appliedKoreanLedEditorialOverrides": applied_overrides,
        **policy_counts,
        "originalEnglishCueCount": len(original),
        "pilotCueCount": len(reduced),
        "cueReduction": len(original) - len(reduced),
        "originalOverlapCount": original_overlaps,
        "pilotOverlapCount": final_overlaps,
        "suppressedOverlappingShortReactions": suppressed,
        "mergedSameSpeakerFragments": merged,
        "combinedIntoReadableCards": cards_combined,
        "groupedEqualStartEvents": equal_starts,
        "clippedOverlappingEnds": clipped,
        "subOneSecondOrHighDensityCueCount": len(fast),
        "medianPilotDurationSeconds": round(statistics.median(durations), 3),
        "speakerCueCounts": dict(sorted(speaker_counts.items())),
        "speakerLabelMismatchFlagCount": len(mismatches),
        "speakerLabelMismatchExamples": mismatches[:40],
        "limitations": [
            "The candidate is a mechanical readability prototype, not a completed semantic review.",
            "Korean-aligned speaker mismatches and dense cues require contextual editorial decisions.",
            "Song and lyric ranges require a dedicated Korean-led copyright audit before publication.",
            "No public website, repository manifest, commit, push, or deployment was changed.",
        ],
    }
    atomic_write_text(work / "candidate.diagnostic.vtt", candidate_vtt(reduced))
    atomic_write_json(work / "pilot-report.json", report)
    markdown = f"""# VLAST-assisted subtitle pilot: {args.video_id}

Status: diagnostic local prototype; not publication-ready.

## Result

- Korean is the authoritative content reference.
- Original English cues: {len(original)}
- Korean-led sample corrections applied: {applied_overrides}
- Standalone `ja` markers restored from Korean: {policy_counts['restoredStandaloneJaMarkers']}
- Lyric events replaced with descriptions: {policy_counts['replacedLyricEvents']}
- Readability-pilot cues: {len(reduced)} ({len(original) - len(reduced)} fewer)
- Overlapping cue pairs: {original_overlaps} before, {final_overlaps} after
- Suppressed overlapping short reactions: {suppressed}
- Merged same-speaker fragments: {merged}
- Combined source cues into readable conversation cards: {cards_combined}
- Clipped overlapping ends that could otherwise reappear: {clipped}
- Remaining sub-one-second or high-density cues: {len(fast)}
- Korean/English speaker-label mismatches flagged for context review: {len(mismatches)}
- Median pilot cue duration: {statistics.median(durations):.3f} seconds

## Interpretation

The source already contains explicit speaker abbreviations for all five members, so
speaker colors are technically straightforward. Names must remain visible because
the color is supplemental. Hamin should use a readable green on the dark overlay.

The timing problem is measurable: overlapping source cues can make an older line
return after a short interjection. This prototype removes that behavior by
suppressing only narrow low-information overlaps, merging safe same-speaker
fragments, and clipping superseded cue ends. Remaining dense cues and every
speaker-label mismatch still need a Korean-led contextual pass.

## Publication boundary

This pilot deliberately does not claim full semantic or song-lyric review. It has
not changed the public subtitle directories, manifests, website, Git history, or
deployment. A separate validator and sealed publication path are required for the
new workflow before it can coexist safely with the preserved full-translation
workflow.
"""
    atomic_write_text(work / "pilot-report.md", markdown)

    progress = read_json(work / "translation-progress.json")
    progress["status"] = "diagnostic-candidate-built"
    progress["updatedAt"] = now
    progress["decisions"] = [
        "Use Korean captions as the authoritative semantic and structural reference.",
        "Treat English captions as an editable draft, never as semantic authority.",
        "Suppress only overlapping low-information reactions in the deterministic first pass.",
        "Merge only same-speaker fragments with tight timing and bounded combined length.",
        "Combine tightly timed speech into at most two visible speaker lines per conversation card.",
        "Clip superseded cue endings to prevent an earlier line from reappearing.",
        "Keep visible speaker names even if optional member colors are later enabled.",
    ]
    progress["speakerNotes"] = [
        {"code": code, "name": name, "cueCount": speaker_counts.get(code, 0)}
        for code, name in SPEAKER_NAMES.items()
    ]
    progress["uncertainties"] = mismatches
    progress["reviewSamples"] = overrides
    progress["safeSourcePolicies"] = policy_counts
    progress["confirmedSongRanges"] = song_ranges
    atomic_write_json(work / "translation-progress.json", progress)
    print(
        f"Built diagnostic pilot for {args.video_id}: {len(original)} -> {len(reduced)} cues, "
        f"overlaps {original_overlaps} -> {final_overlaps}, {len(mismatches)} speaker flags."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}")
        raise SystemExit(1)
