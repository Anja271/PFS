#!/usr/bin/env python3
"""Create a Korean-led editorial risk ledger for VLAST-assisted captions."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / ".subtitle-work"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
SPEAKER_PREFIX_RE = re.compile(r"^(?:예준|노아|밤비|은호|하민|YJ|NA|BB|EH|HM):\s*")
STANDALONE_JA_RE = re.compile(r"(?<![가-힣])자(?![가-힣])")
HANGUL_RE = re.compile(r"[가-힣]")
LATIN_RE = re.compile(r"[A-Za-z]")
ENGLISH_PRONOUN_RE = re.compile(
    r"\b(?:he|he's|him|his|she|she's|her|hers|they|they're|them|their|theirs)\b",
    re.I,
)
SUSPICIOUS_ENGLISH_RE = re.compile(
    r"\b(?:bread[- ]bread|poem|nose job|social need|circuit manager|flea|playa|"
    r"bambi|banbi|ha-min|eun-ho|ye-jun|mr\.|brother|big brother|bro)\b",
    re.I,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def source_span_events(start: int, end: int, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for candidate in events:
        candidate_start = int(candidate["startMs"])
        if start <= candidate_start < end:
            result.append(candidate)
        if candidate_start >= end:
            break
    return result


def body(text: str) -> str:
    return SPEAKER_PREFIX_RE.sub("", text, count=1).strip()


def latin_heavy(text: str) -> bool:
    cleaned = body(text)
    return len(LATIN_RE.findall(cleaned)) >= 10 and not HANGUL_RE.search(cleaned)


def song_candidates(korean: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in korean:
        if not latin_heavy(str(event.get("text") or "")):
            if current:
                runs.append(current)
                current = []
            continue
        if current and int(event["startMs"]) - int(current[-1]["startMs"]) > 12000:
            runs.append(current)
            current = []
        current.append(event)
    if current:
        runs.append(current)
    candidates = []
    for run in runs:
        start = int(run[0]["startMs"])
        end = int(run[-1]["startMs"]) + max(200, int(run[-1].get("durationMs") or 0))
        if len(run) >= 2 and end - start >= 5000:
            candidates.append(
                {
                    "startMs": start,
                    "endMs": end,
                    "eventCount": len(run),
                    "status": "requires-contextual-song-audit",
                    "sample": [str(item.get("text") or "") for item in run[:4]],
                }
            )
    return candidates


def issue_ledger(
    korean: list[dict[str, Any]], english: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], Counter[str]]:
    issues = []
    counts: Counter[str] = Counter()
    for index, event in enumerate(english):
        start = int(event["startMs"])
        end = (
            int(english[index + 1]["startMs"])
            if index + 1 < len(english)
            else start + max(300, int(event.get("durationMs") or 0))
        )
        related = source_span_events(start, end, korean)
        korean_text = " ".join(str(item.get("text") or "") for item in related)
        english_text = str(event.get("text") or "")
        reasons = []
        korean_ja_count = len(STANDALONE_JA_RE.findall(korean_text))
        english_ja_count = len(re.findall(r"\bja\b", english_text, flags=re.I))
        if korean_ja_count > english_ja_count:
            reasons.append("missing-standalone-ja")
        if "형" in korean_text and not re.search(r"\bhyung\b", english_text, flags=re.I):
            reasons.append("missing-hyung")
        if re.search(r"두[두도]?한|두두|두도", korean_text) and "dudu" not in english_text.lower():
            reasons.append("possible-missing-dudu-wordplay")
        if re.search(r"봉(?:국|극|구스|커스|끝)", korean_text) and not re.search(
            r"Bong(?:uk|us|-kkeut|-end)", english_text, flags=re.I
        ):
            reasons.append("possible-missing-bong-wordplay")
        if SUSPICIOUS_ENGLISH_RE.search(english_text):
            reasons.append("suspicious-machine-term")
        if ENGLISH_PRONOUN_RE.search(english_text) and len(related) > 0:
            reasons.append("third-person-context-audit")
        duration = max(0.2, int(event.get("durationMs") or 0) / 1000)
        if duration < 1 or len(english_text) / duration > 28:
            reasons.append("source-readability-risk")
        if reasons:
            for reason in reasons:
                counts[reason] += 1
            issues.append(
                {
                    "startMs": int(event["startMs"]),
                    "reasons": reasons,
                    "korean": [str(item.get("text") or "") for item in related],
                    "english": english_text,
                    "status": "pending-context-review",
                }
            )
    return issues, counts


def reviewed_range_for(
    start: int, reviewed_ranges: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for reviewed_range in reviewed_ranges:
        if (
            reviewed_range.get("status") == "reviewed"
            and int(reviewed_range["startMs"]) <= start < int(reviewed_range["endMs"])
        ):
            return reviewed_range
    return None


def review_chunks(
    duration_seconds: int,
    issues: list[dict[str, Any]],
    reviewed_ranges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunk_ms = 10 * 60 * 1000
    chunks = []
    for start in range(0, duration_seconds * 1000, chunk_ms):
        end = min(duration_seconds * 1000, start + chunk_ms)
        chunk_issues = [item for item in issues if start <= item["startMs"] < end]
        reason_counts = Counter(
            reason for item in chunk_issues for reason in item.get("reasons", [])
        )
        reviewed_range = next(
            (
                item
                for item in reviewed_ranges
                if item.get("status") == "reviewed"
                and int(item["startMs"]) == start
                and int(item["endMs"]) == end
            ),
            None,
        )
        chunks.append(
            {
                "startMs": start,
                "endMs": end,
                "status": "reviewed" if reviewed_range else "pending-context-review",
                "issueCount": len(chunk_issues),
                "reasonCounts": dict(sorted(reason_counts.items())),
                **(
                    {
                        "reviewedAt": reviewed_range.get("reviewedAt"),
                        "reviewPasses": reviewed_range.get("reviewPasses"),
                    }
                    if reviewed_range
                    else {}
                ),
            }
        )
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args()
    if not VIDEO_ID_RE.fullmatch(args.video_id):
        raise RuntimeError("invalid YouTube video ID")
    work = WORK_ROOT / args.video_id / "vlast-assisted"
    metadata = read_json(work / "pilot-metadata.json")
    progress = read_json(work / "translation-progress.json")
    reviewed_ranges = progress.get("reviewedContextRanges") or []
    if not isinstance(reviewed_ranges, list):
        raise RuntimeError("reviewedContextRanges must be a list")
    temporary = Path(str(metadata.get("temporarySourceDirectory") or ""))
    korean = read_json(temporary / "korean-events.json")
    english = read_json(temporary / "english-events.json")
    issues, issue_counts = issue_ledger(korean, english)
    overrides = read_json(work / "editorial-overrides.json")
    reviewed_starts = {int(item["startMs"]) for item in overrides}
    handled_ja_issue_count = 0
    for issue in issues:
        if issue["startMs"] in reviewed_starts:
            issue["status"] = "resolved-by-editorial-override"
            continue
        if "missing-standalone-ja" in issue["reasons"]:
            issue["reasons"] = [
                reason for reason in issue["reasons"] if reason != "missing-standalone-ja"
            ]
            handled_ja_issue_count += 1
            if not issue["reasons"]:
                issue["status"] = "resolved-by-safe-source-policy"
        if issue["status"] == "pending-context-review" and reviewed_range_for(
            int(issue["startMs"]), reviewed_ranges
        ):
            issue["status"] = "resolved-by-full-context-review"
    pending_issues = [item for item in issues if item["status"] == "pending-context-review"]
    resolved_issues = [item for item in issues if item["status"] != "pending-context-review"]
    pending_counts = Counter(
        reason for item in pending_issues for reason in item.get("reasons", [])
    )
    songs = song_candidates(korean)
    chunks = review_chunks(
        int(metadata["durationSeconds"]), pending_issues, reviewed_ranges
    )
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    audit = {
        "version": 1,
        "youtubeId": args.video_id,
        "generatedAt": now,
        "status": "editorial-review-required",
        "issueCount": len(issues),
        "issueReasonCounts": dict(sorted(issue_counts.items())),
        "pendingIssueCount": len(pending_issues),
        "pendingIssueReasonCounts": dict(sorted(pending_counts.items())),
        "resolvedIssueCount": len(resolved_issues),
        "handledStandaloneJaIssueCount": handled_ja_issue_count,
        "songCandidateCount": len(songs),
        "songCandidates": songs,
        "reviewChunks": chunks,
        "issues": issues,
    }
    atomic_write_json(work / "quality-audit.json", audit)
    progress["status"] = (
        "review-complete"
        if chunks and all(chunk["status"] == "reviewed" for chunk in chunks)
        else "full-context-review-queued"
    )
    progress["updatedAt"] = now
    progress["qualityAudit"] = {
        "issueCount": len(issues),
        "pendingIssueCount": len(pending_issues),
        "pendingIssueReasonCounts": dict(sorted(pending_counts.items())),
        "resolvedIssueCount": len(resolved_issues),
        "songCandidateCount": len(songs),
        "reviewChunks": chunks,
        "source": "quality-audit.json",
    }
    atomic_write_json(work / "translation-progress.json", progress)
    print(
        f"Queued {len(pending_issues)} pending Korean-led review items in {len(chunks)} context chunks; "
        f"found {len(songs)} possible song ranges."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Error: {error}")
        raise SystemExit(1)
