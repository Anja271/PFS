# PLAVE Livestream Fan-Subtitle Translation Guide

This document defines the permanent translation and quality rules for English fan subtitles on this site. Apply it to every livestream together with `docs/plave-glossary.md`.

## Priorities

When rules compete, use this order:

1. Preserve every source start timestamp exactly.
2. Do not reproduce, reconstruct, or translate copyrighted song lyrics.
3. Do not invent dialogue, speakers, context, jokes, names, or song titles.
4. Preserve the meaning, tone, humor, and relationship dynamics of the Korean speech.
5. Write natural, concise, internationally understandable English.
6. Keep each cue readable in its available time.

Technical or copyright failures block publication. Linguistic uncertainty must be handled conservatively and recorded in the review report.

## Source handling

- Treat the Korean transcript as ASR evidence, not as infallible dialogue.
- Normalize Windows and Unix line endings before parsing.
- Parse and store all source timestamps programmatically before translating.
- Preserve source order.
- Merge entries with the same start timestamp into one source cue, retaining their content in source order.
- Never overwrite the downloaded source transcript.
- Build from a structured intermediate representation so missing timestamps can be detected mechanically.
- Use PLAVE reference material only to resolve spellings, terminology, relationships, and plausible references. Never insert a fact merely because it appears in reference material.

## Full-stream and highlight modes

- A **full-stream** job translates every unique source timestamp and uses `chapters.json` for broad navigation.
- A **highlight** job translates every source timestamp inside each approved scene and no timestamps outside those scenes. It uses `scenes.json` objects with exactly `startSeconds`, `endSeconds`, and `title`.
- In highlight mode, cue end times still come from the following timestamp in the complete source, not merely the next translated cue.
- A heatmap range plus automatic padding is discovery input only. Read wider context, then replace it with semantic boundaries that contain the setup, popular moment, and immediate resolution.
- Do not cut through a question and answer, running joke, call, story, game round, role-play, performance and reaction, or unresolved speaker exchange.
- Do not extend a highlight through an unrelated later activity merely to create a large continuous range.

## Immutable timing rules

- Every unique source start timestamp must appear exactly once in the final VTT.
- Do not invent, shift, round, reorder, or omit start timestamps.
- Format every timestamp as `HH:MM:SS.mmm`.
- A cue ends exactly one millisecond before the following source start timestamp.
- Cues must not overlap or touch.
- Give the final cue a short, sensible positive duration, normally about six seconds unless the source supplies a better safe endpoint.
- The file must begin with `WEBVTT`, followed by one blank line.
- Do not add cue positioning, styling instructions, colors, or HTML.

## Translation style

- Translate spoken Korean idiomatically rather than word for word.
- Preserve teasing, affectionate exaggeration, intentional repetition, running jokes, and member-specific tone.
- Remove only obvious ASR duplication and meaningless recognition stutters.
- Do not erase meaningful hesitation, comic timing, or deliberate repetition.
- Prefer concise subject–verb sentences over literal Korean clause stacking.
- Resolve omitted Korean subjects only when grammar and the surrounding exchange support the choice.
- Use em dashes or two dialogue lines to show short exchanges inside one cue. Do not add speaker names unless the source actually says them or identification is essential to prevent confusion.
- Never use `innerHTML`-style markup or HTML tags in subtitle text.

## Conversation continuity

Do not translate conversational cues in isolation.

- Read at least the preceding and following several cues before deciding the meaning of a line.
- For calls, stories, games, and extended jokes, identify the entire scene boundary first and review it as one unit.
- Maintain a temporary speaker ledger for the scene: confirmed speaker, addressee, relationship, topic, and unresolved turns.
- Check that questions receive plausible answers and pronouns remain consistent across cue boundaries.
- Use later self-identification or conversation evidence to correct an earlier ASR speaker error.
- A voice, impression, catchphrase, or hobby can be a clue but is not proof by itself.
- Do not mistake a member imitating another member for an actual speaker change.
- When a line only becomes coherent after correcting an ASR subject, make the smallest supported correction and record it in the review report.
- Re-read every long conversation continuously after translation. A technically correct cue can still be wrong in the dialogue flow.

### Omitted Korean subjects, objects, and addressees

Korean frequently omits arguments that English requires. Do not resolve them from an isolated cue or from punctuation generated by ASR.

- Classify each restored speaker, subject, object, or addressee as **confirmed**, **strongly supported**, or **unclear**.
- Confirmed evidence includes an explicit name or pronoun, a uniquely identifying form of address, reliable self-identification, or supplied audio/visual context.
- Strong support requires several agreeing signals across the scene, such as a direct question-answer pair, stable first-person viewpoint, established ownership, response morphology, and coherent turn-taking.
- A pause, caption boundary, personality stereotype, hobby, catchphrase, or damaged name is never sufficient by itself.
- Use explicit `I`, `you`, `we`, `he`, `she`, or a member name only for confirmed or strongly supported readings.
- When evidence remains unclear, prefer natural neutral English that does not assign a participant. If neutrality would change the meaning, use the narrowest supported reading and document the alternatives.
- In the editorial pass, audit every English pronoun or named participant that was not explicit in Korean and correct unsupported assignments directly.

## `hyung` and forms of address

`형` is a hard terminology rule.

- Render culturally or relationally meaningful `형` as `hyung`.
- Use forms such as `Yejun-hyung`, `Noah-hyung`, or simply `hyung`, according to the Korean line.
- When a younger member addresses Bamby, forms such as `Bonggu-hyung` may be appropriate if the name is spoken.
- Never translate `형` as `bro`, `brother`, `big brother`, or `Mr.`.
- Do not attach `hyung` to a member who is younger than the speaker.
- Do not invent `hyung` where the Korean does not contain it merely to label a speaker.
- Translate `씨` according to tone, usually with the name alone. Do not automatically use `Mr.`.

The validator must reject `bro`, `brother`, automatic `Mr.`, common misspellings of `hyung`, and malformed member-name combinations.

## Damaged or ambiguous ASR

Use the narrowest justified interpretation:

1. Check Korean grammar and likely spacing.
2. Check the immediate question-and-answer flow.
3. Check repeated wording elsewhere in the same scene.
4. Check the glossary and trusted PLAVE context.
5. Prefer a neutral translation if the evidence remains incomplete.

Do not create a polished but unsupported replacement line. If a name, title, object, number code, or insider cannot be established reliably:

- omit the uncertain proper name when the sentence still works;
- use a cautious generic reference;
- romanize a spoken wordplay when translation would destroy it;
- or use a short neutral description.

When a wordplay cannot be made natural in English without inventing a new joke, use a concise description such as `[They make a Korean pun on “highlighter” and “fan”]`. Record the original terms and the lost sound relationship in the review report rather than forcing an unfunny literal translation.

Record material uncertainty with timestamp, Korean source, chosen English, and reason in the review report. Bracketed uncertainty such as `[unclear]` should be rare and used only when even a neutral rendering would mislead.

## Songs and music

Copyrighted lyrics must not be reconstructed, completed, transliterated, or translated, even when fragments appear in the ASR.

- Replace lyric-only cues with concise descriptions such as `[Bamby sings]`, `[Singing]`, `[Bamby sings in English]`, `[Bamby sings in Japanese]`, or `[Music]`.
- Preserve every original timestamp inside a lyric sequence. Repeated descriptions are acceptable when required for timestamp coverage.
- A verified title may appear as `[Bamby sings “Song Title”]` only when the supplied source clearly establishes it.
- Never guess a song title from damaged lyrics.
- Translate non-lyrical laughter, comments, interruptions, and spoken reactions during music normally.
- If someone quotes or alludes to a lyric during conversation, describe the action without reproducing the lyric, for example `[Noah quotes a lyric about affectionate nagging]`.

Narrow exception: when the user directly supplies a short, compact lyric or fan-call excerpt and explicitly requests its translation, translate only that supplied unit. Do not extend it with neighboring caption text, reconstruct a longer verse, or treat it as permission to translate the whole performance. Identify the exact translated excerpt and the user-supplied exception in the review report.

## Sound descriptions

Use concise, consistent descriptions where they matter:

- `[음악]` → `[Music]`
- `[노래]` → `[Singing]`
- `[웃음]` → `[Laughs]`
- `[한숨]` → `[Sighs]`
- `[목을 가다듬음]` → `[Clears throat]`
- `[헉 소리]` → `[Gasps]`
- `[숨을 헐떡임]` → `[Panting]`

Translate `[콧방귀]` contextually as `[Snorts]` or `[Chuckles]`, or omit it if it has no communicative value.

## Readability

- Use no more than two text lines per cue.
- Prefer natural phrase boundaries for line breaks.
- Keep the English short enough for the cue duration; very short cues may require substantial but faithful compression.
- Run duration-aware density checks in addition to the two-line check. Dense one- and two-second cues must be shortened or explicitly confirmed as justified rapid chants, repetitions, names, or sound descriptions.
- Treat density findings as editorial warnings rather than blind failures: rapid call-and-response can be correct even when ordinary prose at the same length would be unreadable.
- Preserve essential meaning before conversational filler.
- Avoid long explanatory text inside subtitles. Put explanations in the review report.
- Use plain punctuation and readable international English.

## Required two-pass workflow

### Two approval gates

The long translation and review phase must not require the user to remain present.

1. **Preparation approval:** run `scripts/prepare_stream.py` once. This is the only network-bearing source-preparation step. It stores metadata, Korean captions, heatmap data, normalized cues, a scene plan, and resumable job state under `.subtitle-work/<VIDEO_ID>/`.
2. **Unattended local work:** translate, review, correct, and validate using only the prepared files. Do not make additional network requests merely to repeat information already present in the work directory. Save progress in the work directory so an interrupted job resumes rather than restarts.
3. **Publication approval:** after `scripts/finalize_subtitle_job.py` has sealed a passing package, stop and request a separate explicit approval. Only then may `scripts/publish_subtitle_job.py --confirm-publication` copy, commit, and push it.

Never publish during preparation, translation, review, or validation. A prompt asking for subtitle creation is not by itself approval to publish.

Before publication changes any public file, the publisher must preflight every required import and generator, require a clean tracked worktree, fetch `origin/main`, and fast-forward only when local `main` is strictly behind. Local-ahead or diverged history requires inspection instead of silently pushing unrelated commits. If a failure occurs before commit, restore every allow-listed file to its pre-publication state.

### Limited parallel scene work

Independent scenes may be translated in parallel only when doing so cannot break conversation continuity.

- First establish complete scene boundaries and retain contextual overlap around every scene.
- A scene is independent only if no phone call, story, game round, role-play, sustained joke, speaker-identification problem, or question-and-answer exchange crosses its boundary.
- Adjacent fragments of the same conversation are never independent merely because a heatmap or chapter boundary separates them.
- Record the shared glossary, known speakers, unresolved identities, song ranges, and terminology decisions before parallel work begins.
- Each worker must return timestamp-complete scene output plus uncertainties and speaker evidence.
- Use one compact scene artifact with `scene`, `title`, `startSeconds`, `endBoundarySeconds`, `cues`, `uncertainties`, and `speakerNotes`. Store cues as `[startSeconds, translation]` pairs to reduce fragile large writes.
- Save long scene artifacts in small progress chunks so a stalled write does not discard a completed translation.
- Merge scenes in source order, then perform one sequential editorial pass across every boundary and one global terminology/pronoun/song audit.
- If independence is uncertain, process the scenes sequentially.

### Pass 1: translation

- Translate all cues in order with contextual overlap between sections.
- Maintain timestamp coverage continuously.
- Mark uncertain decisions in structured notes.
- Replace song lyrics during this pass, not afterward.

### Pass 2: editorial review

- Review scenes rather than isolated cues.
- Repair speaker attribution, question-and-answer logic, pronouns, and repeated terminology.
- Audit every occurrence of `hyung` and every member name.
- Recheck song boundaries and remove any surviving lyric fragments.
- Tighten cues that are too long for their duration.
- Correct the VTT directly; do not merely list defects.
- Keep generated coverage/validation summaries separate from editorial notes, or merge them without overwriting reviewed uncertainty and terminology decisions.

## Chapter navigation

Create a chapter list during or immediately after the scene-level translation, while the complete conversation structure is still available.

- Create `chapters/<VIDEO_ID>.json` alongside the final VTT.
- Use a JSON list of objects with exactly `startSeconds` and `title`.
- Every `startSeconds` value must be a non-negative integer that corresponds exactly to an existing source/VTT cue start.
- Start with the first available source cue so viewers can jump to the beginning of the translated material.
- Keep chapters strictly increasing and cover the complete stream through its closing section.
- Use broad, meaningful scene boundaries. Do not create a chapter for every joke, short tangent, song fragment, or individual cue.
- As a guideline, a two-hour conversational livestream normally needs roughly 10–20 chapters. Adapt to the actual structure rather than forcing a fixed interval.
- Prefer concise, natural English titles that describe the subject or activity without inventing context.
- Do not reproduce song lyrics in chapter titles. A reliably established song or segment title may be named.
- Do not use unclear ASR fragments as titles. Use a broader supported description instead.

Example:

```json
[
  {
    "startSeconds": 254,
    "title": "Opening and Monday check-in"
  },
  {
    "startSeconds": 1937,
    "title": "Reviewing the 'Meccha Suki' video"
  }
]
```

Review the chapter list against the complete translated scene outline. The website manifest generator validates filenames, titles, ordering, and start values before publication.

## Highlight scene navigation

- Create `.subtitle-work/<VIDEO_ID>/scenes.json` for highlight jobs.
- Each scene must use exactly `startSeconds`, `endSeconds`, and `title`.
- `startSeconds` must match the first selected VTT/source cue in the scene; `endSeconds` is the exclusive semantic boundary.
- Scenes must be strictly ordered and non-overlapping. Every translated cue must lie in exactly one scene.
- Use recognizable natural titles based on the translated scene, not raw heatmap labels or damaged ASR.
- The Most replayed peak must lie inside the scene, but the peak itself does not determine the final scene boundary.

## Publication gates

Before a subtitle file can be published, automated validation must confirm:

- valid UTF-8;
- `WEBVTT` header and blank line;
- valid start and end timestamps;
- strictly increasing unique start timestamps;
- exactly one VTT cue per unique source timestamp;
- no missing or additional start timestamps;
- duplicate source timestamps merged correctly;
- each end time after its start and exactly one millisecond before the next start;
- no overlaps;
- one or two non-empty text lines per cue;
- duration-aware warnings for unusually dense short cues, followed by documented editorial review;
- no HTML or positioning instructions;
- no forbidden `bro`, `brother`, automatic `Mr.`, or malformed `hyung` forms;
- no known lyric text from source lyric blocks.

Chapter validation must also confirm:

- a valid video-ID filename;
- a non-empty JSON list;
- strictly increasing non-negative integer start values;
- every chapter start matches an existing VTT cue start;
- the first chapter matches the first translated cue;
- complete high-level coverage without excessively narrow sections;
- concise, supported titles without lyric text.

Highlight validation must also confirm:

- valid, strictly ordered, non-overlapping semantic scene boundaries;
- every scene start matches its first selected VTT cue;
- every translated cue lies inside exactly one declared scene;
- complete timestamp coverage inside the declared ranges and no timestamps outside them;
- cue end times follow the complete-source timeline;
- concise, supported scene titles.

If validation fails, do not replace an existing published VTT. Write to a temporary path first and promote the file only after every gate passes.

## Review report

For each video, retain a concise Markdown report containing:

- raw and unique source timestamp counts;
- generated cue count;
- first and last timestamps;
- coverage, ordering, overlap, line-count, terminology, and UTF-8 results;
- all materially uncertain passages;
- important terminology and wordplay choices;
- song-handling decisions;
- any scene-level speaker inferences;
- the exact validator command and result.
- for full jobs: chapter count, first and last chapter, and chapter validation result;
- for highlight jobs: scene count, boundaries, titles, contained heatmap peaks, and partial-coverage validation result.

After pushing, check the newest successor Pages deployment rather than assuming the first run for the publication commit is authoritative. An update workflow may push regenerated data and intentionally supersede or cancel that first Pages run. Require the newest Pages run to succeed, confirm the public manifest includes the video, and verify the public VTT URL is reachable.

Automated fan subtitles should be identified as automated and potentially imperfect when no human review has occurred.
