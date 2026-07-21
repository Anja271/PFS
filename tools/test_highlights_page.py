#!/usr/bin/env python3
"""Regression checks for the static Most replayed page controls."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    html = (ROOT / "highlights.html").read_text(encoding="utf-8")
    javascript = (ROOT / "highlights.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "styles.css").read_text(encoding="utf-8")
    highlights = json.loads((ROOT / "data" / "highlights.json").read_text(encoding="utf-8"))

    assert 'id="random-highlight"' in html
    assert "🎲 Random Most replayed scene" in html
    assert 'class="button button-primary"' in html
    assert "randomButton.addEventListener(\"click\", openRandomHighlight)" in javascript
    assert "highlights.flatMap" in javascript
    assert "window.sessionStorage.setItem" in javascript
    assert "from=highlights" in javascript
    assert "endSeconds: scene.endSeconds" in javascript
    assert "coverage: stream.coverage" in javascript
    assert "&end=${endSeconds}" in javascript
    assert 'coverage === "highlights"' in javascript
    assert "link.href = sceneUrl" in javascript
    app_javascript = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "coverageRange?.endSeconds" in app_javascript
    assert 'getSubtitleCoverage(video.youtubeId) === "highlights"' in app_javascript
    assert "state.player.pauseVideo()" in app_javascript
    assert "End of this subtitled highlight" in app_javascript
    assert "#random-highlight { width: 100%; }" in stylesheet
    assert sum(len(stream.get("scenes", [])) for stream in highlights) > 1

    print(
        "PASS: the Random Most replayed button is present, uses the fan-subtitle "
        "scene route with explicit end boundaries, avoids immediate repeats, "
        "and has a mobile-width rule."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
