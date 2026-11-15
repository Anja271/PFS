"""Regression checks for two reviewed excerpts of one guest video."""
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST = r"""
const { readFileSync } = require("node:fs");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const source = readFileSync("app.js", "utf8").replace(/\}\)\(\);\s*$/, `
  globalThis.app = { state, normalizeGuestVideos, getSubtitleCoverage, route, parseVtt,
    setView(fn) { showPlayerView = fn; } };
})();`);
const window = { location: { search: "" } };
const context = { window, URLSearchParams, document: { addEventListener() {}, getElementById() {} } };
vm.runInNewContext(source, context);
const app = context.app;
const manifest = JSON.parse(readFileSync("data/guest-videos.json", "utf8"));
const id = "WiIqJOpPycA";
const entries = manifest.filter((item) => item.youtubeId === id);
assert.equal(entries.length, 2);
app.state.guests = app.normalizeGuestVideos([...manifest, ...entries], []);
assert.equal(app.state.guests.size, new Set(manifest.map((item) => item.youtubeId)).size);
assert.equal(app.normalizeGuestVideos(entries, [{ youtubeId: id }]).size, 0);
assert.equal(app.getSubtitleCoverage(id), "guest");
const calls = [];
app.setView((video, start, fromHighlights, end) => {
  calls.push([video.youtubeId, start, end, video.skips[0]?.from ?? null, video.skips[0]?.to ?? null]);
});
window.location.search = `?v=${id}&excerpt=first-impressions&t=1&end=10`;
app.route();
assert.deepEqual(calls.pop(), [id, 1560, 4075, null, null]);
window.location.search = `?v=${id}`;
app.route();
assert.deepEqual(calls.pop(), [id, 21449, 22851, 22638, 22779.360]);
const cues = app.parseVtt(readFileSync(`guest-subtitles/${id}.vtt`, "utf8"));
assert.equal(cues.filter((cue) => cue.start >= 1560 && cue.end <= 4075).length, 442);
assert(cues.some((cue) => cue.start >= 22779.360 && cue.end <= 22851));
assert(cues.every((cue, i) => !i || cues[i - 1].end <= cue.start));
assert(cues.every((cue) => entries.some((entry) => cue.start >= entry.startSeconds && cue.end <= entry.endSeconds)));
"""


class GuestExcerptTest(unittest.TestCase):
    def test_routes_and_subtitle_ranges(self):
        subprocess.run(["node", "-e", TEST], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
