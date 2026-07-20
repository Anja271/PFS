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

Record material uncertainty with timestamp, Korean source, chosen English, and reason in the review report. Bracketed uncertainty such as `[unclear]` should be rare and used only when even a neutral rendering would mislead.

## Songs and music

Copyrighted lyrics must not be reconstructed, completed, transliterated, or translated, even when fragments appear in the ASR.

- Replace lyric-only cues with concise descriptions such as `[Bamby sings]`, `[Singing]`, `[Bamby sings in English]`, `[Bamby sings in Japanese]`, or `[Music]`.
- Preserve every original timestamp inside a lyric sequence. Repeated descriptions are acceptable when required for timestamp coverage.
- A verified title may appear as `[Bamby sings “Song Title”]` only when the supplied source clearly establishes it.
- Never guess a song title from damaged lyrics.
- Translate non-lyrical laughter, comments, interruptions, and spoken reactions during music normally.
- If someone quotes or alludes to a lyric during conversation, describe the action without reproducing the lyric, for example `[Noah quotes a lyric about affectionate nagging]`.

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
- Preserve essential meaning before conversational filler.
- Avoid long explanatory text inside subtitles. Put explanations in the review report.
- Use plain punctuation and readable international English.

## Required two-pass workflow

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
- chapter count, first and last chapter, and chapter validation result.

Automated fan subtitles should be identified as automated and potentially imperfect when no human review has occurred.
