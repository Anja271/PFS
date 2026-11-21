#!/usr/bin/env python3
"""Check original-channel links without starting any video or audio."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEST = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
function node(tag) {
  return {tag, children: [], attrs: {}, appendChild(child) {this.children.push(child);},
    append(...children) {this.children.push(...children);},
    setAttribute(key, value) {this.attrs[key] = value;}};
}
const source = fs.readFileSync('app.js', 'utf8').replace(/\}\)\(\);\s*$/,
  'globalThis.channelTest = {normalizeGuestVideos, appendCreatorCredit, createCreatorCard};})();');
const context = {document: {addEventListener() {}, getElementById() {return null;},
  createElement: node}};
vm.runInNewContext(source, context);
const app = context.channelTest;
for (const file of ['data/guest-videos.json', 'data/fan-edit-videos.json']) {
  const raw = JSON.parse(fs.readFileSync(file));
  const videos = app.normalizeGuestVideos(raw, []);
  for (const video of videos.values()) {
    assert.match(video.creatorUrl, /^https:\/\/www\.youtube\.com\/@/);
    const heading = node('h2');
    app.appendCreatorCredit(heading, video);
    const credit = heading.children[0];
    assert.equal(credit.textContent, 'Original channel: ');
    assert.equal(credit.children[0].textContent, video.creator);
    assert.equal(credit.children[0].href, video.creatorUrl);
    assert.equal(credit.children[0].target, '_blank');
    assert.equal(credit.children[0].rel, 'noopener noreferrer');
    const card = app.createCreatorCard(video);
    assert.equal(card.children[0].children[0].children[1].className, 'original-channel');
  }
  for (const creatorUrl of ['javascript:alert(1)', 'https://evil.example/@fake',
    'https://www.youtube.com.evil.example/@fake', 'https://www.youtube.com/watch?v=abcdefghijk']) {
    const video = app.normalizeGuestVideos([{...raw[0], creatorUrl}], []).values().next().value;
    assert.equal(video.creatorUrl, '');
    const heading = node('h2');
    app.appendCreatorCredit(heading, video);
    assert.equal(heading.children[0].children[0].tag, 'span');
  }
}
const official = node('h2');
app.appendCreatorCredit(official, {title: 'Official'});
assert.equal(official.children.length, 0);
assert.match(source, /appendCreatorCredit\(elements\.playerTitle, video\)/);
assert.match(source, /appendCreatorCredit\(document\.getElementById\("creator-title"\), guest\)/);
console.log('PASS: original-channel attribution on cards, chapter pages and player; safe URLs and plain-text fallback.');
"""
if __name__ == "__main__":
    subprocess.run(["node", "-e", TEST], cwd=ROOT, check=True)
