#!/usr/bin/env python3
"""Fan-edit isolation, continuous coverage and independent visual translations."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEST = r'''
const {readFileSync}=require('node:fs');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const nodes=new Map(),fetches=[],calls=[],window={location:{search:''}};
const document={addEventListener(){},getElementById(id){
  if(!nodes.has(id))nodes.set(id,{classList:{toggle(){},remove(){}},setAttribute(){}});
  return nodes.get(id);
}};
const source=readFileSync('app.js','utf8').replace(/\}\)\(\);\s*$/,`
 globalThis.test={state,normalizeGuestVideos,normalizeGuestChapters,normalizeVisualCaptions,
   guestChapterRuns,guestDetailUrl,getSubtitleCoverage,loadVtt,updateSubtitles,resetSubtitleDisplay,
   route,setView(fn){showPlayerView=fn;}};
})();`);
const context={document,window,URLSearchParams,async fetch(path){fetches.push(path);
 return {ok:true,text:async()=>readFileSync(path,'utf8'),json:async()=>JSON.parse(readFileSync(path,'utf8'))};}};
vm.runInNewContext(source,context);
const app=context.test;
const records=JSON.parse(readFileSync('data/fan-edit-videos.json'));
assert.ok(records.some(v=>v.youtubeId==='HNdJaZrCkI8'));
assert.equal(new Set(records.map(v=>v.youtubeId)).size,records.length);
app.state.fanEdits=app.normalizeGuestVideos(records,[]);
app.state.guestChapters=app.normalizeGuestChapters(JSON.parse(readFileSync('data/fan-edit-chapters.json')));
app.setView((...args)=>calls.push(args));
for(const record of records){
 const id=record.youtubeId,guest=app.state.fanEdits.get(id);
 assert.equal(app.state.guests.has(id),false);
 assert.equal(app.getSubtitleCoverage(id),'fan-edit');
 assert.equal(app.guestDetailUrl(id),`fan-edits.html?v=${id}`);
 for(const chapter of app.state.guestChapters.get(id)){
  const run=app.guestChapterRuns(guest,chapter)[0];
  assert.equal(run.endSeconds,record.endSeconds);
  window.location.search=`?v=${id}&chapter=${chapter.startSeconds}&t=${run.startSeconds}`;
  app.route();const [video,start,,end]=calls.pop();
  assert.equal(video.youtubeId,id);assert.equal(start,chapter.startSeconds);
  assert.equal(end,record.endSeconds);
 }
}
(async()=>{
 await app.loadVtt('HNdJaZrCkI8');
 assert.equal(fetches.pop(),'fan-edit-captions/HNdJaZrCkI8.json');
 assert.equal(fetches.pop(),'fan-edit-subtitles/HNdJaZrCkI8.vtt');
 assert.equal(app.state.cues.length,135);assert.equal(app.state.visualCaptions.length,11);
 let now=118.5;app.state.player={getCurrentTime:()=>now};app.state.subtitlesEnabled=true;
 app.state.initialEndSeconds=369;app.updateSubtitles();
 assert.match(nodes.get('visual-caption-overlay').textContent,/coffin/);
 now=121;app.updateSubtitles();assert.equal(nodes.get('visual-caption-overlay').textContent,'');
 now=366.5;app.updateSubtitles();assert.match(nodes.get('subtitle-overlay').textContent,/Hamin/);
 assert.match(nodes.get('subtitle-overlay').textContent,/hyung/);
 app.resetSubtitleDisplay('off');assert.equal(nodes.get('visual-caption-overlay').textContent,'');
 assert.equal(app.normalizeVisualCaptions([{start:0,end:2,text:'x',attribution:5}]).length,0);
 assert.equal(app.normalizeVisualCaptions([{start:0,end:2,text:'x',attribution:''},{start:1,end:3,text:'y',attribution:''}]).length,0);
 for(const page of ['index.html','creator-reactions.html','highlights.html','fan-edits.html']){
  assert.ok(readFileSync(page,'utf8').includes('href="fan-edits.html"'));
 }
 console.log('PASS: fan-edit isolation, cue loading, independent visuals and continuous chapter playback.');
})().catch(error=>{console.error(error);process.exit(1)});
'''

if __name__ == '__main__':
    raise SystemExit(subprocess.run(['node', '-e', TEST], cwd=ROOT).returncode)
