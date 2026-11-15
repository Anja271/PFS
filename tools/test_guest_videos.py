#!/usr/bin/env python3
"""Exercise the guest catalogue and bounded player routing without YouTube."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
TEST = r"""
const { readFileSync } = require('node:fs');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = readFileSync('app.js', 'utf8').replace(/\}\)\(\);\s*$/, `
  globalThis.guestTest = { state, normalizeGuestVideos, normalizeGuestChapters, guestChapterRuns,
    createCreatorChapter, route, getSubtitleCoverage, updateSubtitles,
    loadVtt, setView(fn) { showPlayerView = fn; } };
})();`);
const nodes = new Map();
const fetches = [];
const window = {location: {search: ""}};
const context = {
  window, URLSearchParams,
  document: {
    addEventListener() {},
    createElement(tag) {
      return {children: [], tag, append(...nodes) { this.children.push(...nodes); },
        appendChild(node) { this.children.push(node); }};
    },
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, { classList: {remove() {}, toggle() {}}, replaceChildren() {} });
      return nodes.get(id);
    }
  },
  async fetch(path) {
    fetches.push(path);
    return { ok: true, text: async () => 'WEBVTT\n\n05:57:30.000 --> 05:57:32.000\nHello!\n' };
  }
};
vm.runInNewContext(source, context);
const app = context.guestTest;
const guest = {youtubeId: "WiIqJOpPycA", title: "Guest clip", creator: "Solf",
  startSeconds: 21450, endSeconds: 22632};
const official = {youtubeId: "official123", title: "Official"};
app.state.videos = [official];
app.state.guests = app.normalizeGuestVideos([
  guest, {...guest, title: "Duplicate"}, {...guest, youtubeId: official.youtubeId},
  {...guest, youtubeId: "badRange123", endSeconds: guest.startSeconds},
  {...guest, youtubeId: "noCreator12", creator: " "}
], app.state.videos);
assert.equal(app.state.guests.size, 1);
assert.equal(app.state.guests.get(guest.youtubeId).title, guest.title);
assert.equal(app.getSubtitleCoverage(guest.youtubeId), "guest");
assert.equal(app.getSubtitleCoverage(official.youtubeId), null);

const calls = [];
app.setView((video, start, fromHighlights, end) => calls.push([video.youtubeId, start, fromHighlights, end]));
window.location.search = "?v=WiIqJOpPycA&t=1&end=10&from=highlights";
app.route();
assert.deepEqual(calls.pop(), [guest.youtubeId, 21450, false, 22632]);
window.location.search = "?v=official123&t=12&end=34&from=highlights";
app.route();
assert.deepEqual(calls.pop(), [official.youtubeId, 12, true, 34]);

const records = JSON.parse(readFileSync('data/guest-videos.json', 'utf8'));
app.state.guests = app.normalizeGuestVideos(records, []);
app.state.guestChapters = app.normalizeGuestChapters(JSON.parse(readFileSync('data/guest-chapters.json', 'utf8')));
const published = app.state.guests.get(guest.youtubeId);
assert.equal(app.state.guests.size, 1);
assert.equal(published.excerpts.length, 2);
const chapters = app.state.guestChapters.get(guest.youtubeId);
assert.equal(chapters.length, 62);
assert.equal(chapters.at(-1).endSeconds, 36676);
for (const start of [1560, 3540, 3900]) {
  const chapter = chapters.find(c => c.startSeconds === start);
  const run = app.guestChapterRuns(published, chapter)[0];
  assert.equal(run.startSeconds, start);
  assert.equal(run.endSeconds, 4075);
  window.location.search = `?v=${guest.youtubeId}&chapter=${start}&t=${start}&end=${start + 1}`;
  app.route();
  assert.deepEqual(calls.pop(), [guest.youtubeId, start, false, 4075]);
}
const partial = chapters.find(c => c.startSeconds === 20903);
const noSubs = chapters.find(c => c.startSeconds === 4075);
assert.equal(app.createCreatorChapter(published, partial).children[0].children[2].textContent,
  'Partial English subtitles · from 5:57:29');
assert.match(app.createCreatorChapter(published, noSubs).children[0].href, /youtube\.com.*t=4075s/);
window.location.search = `?v=${guest.youtubeId}&excerpt=first-impressions`;
app.route();
assert.deepEqual(calls.pop(), [guest.youtubeId, 1560, false, 4075]);
window.location.search = `?v=${guest.youtubeId}`;
app.route();
assert.deepEqual(calls.pop(), [guest.youtubeId, 21449, false, 22851]);

const chained = app.normalizeGuestVideos([
  {...guest, startSeconds: 0, endSeconds: 10},
  {...guest, excerpt: 'second', startSeconds: 10, endSeconds: 25},
  {...guest, excerpt: 'third', startSeconds: 27, endSeconds: 40}
], []).get(guest.youtubeId);
assert.equal(JSON.stringify(chained.ranges.map(r => [r.startSeconds, r.endSeconds])), '[[0,25],[27,40]]');

let current = 3540;
let pauses = 0;
let seeks = [];
Object.assign(app.state, { subtitlesEnabled: true, initialStartSeconds: 1560, initialEndSeconds: 4075,
  selectedVideo: published, player: { getCurrentTime: () => current, pauseVideo: () => pauses++,
    getPlayerState: () => 1, seekTo: t => seeks.push(t) } });
window.YT = {PlayerState: {PLAYING: 1}};
app.updateSubtitles();
current = 3900;
app.updateSubtitles();
assert.equal(pauses, 0);
current = 4075;
app.updateSubtitles();
assert.equal(pauses, 1);
app.state.highlightEnded = false;
app.state.initialEndSeconds = 22851;
current = 22638;
app.updateSubtitles();
app.updateSubtitles();
assert.deepEqual(seeks, [22779.360]);

(async () => {
  await app.loadVtt(guest.youtubeId);
  assert.deepEqual(fetches, ["guest-subtitles/WiIqJOpPycA.vtt"]);
  assert.equal(app.state.cues.length, 1);
  console.log("PASS: guest catalogue validation, official isolation, bounded routing and guest VTT.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""

if __name__ == "__main__":
    subprocess.run(["node", "-e", TEST], cwd=ROOT, check=True)
