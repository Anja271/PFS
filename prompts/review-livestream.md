# Task: Review and correct a complete PLAVE livestream translation

Perform a second, independent editorial and technical review of the complete English VTT for YouTube video `<VIDEO_ID>`. Correct the VTT directly. Do not merely describe problems, and do not stop after spot-checking a small excerpt.

## Required inputs

Read completely:

1. `docs/subtitle-translation-guide.md`
2. `docs/plave-glossary.md`
3. the structured Korean source for `<VIDEO_ID>`
4. the complete temporary English VTT
5. the translation pass's uncertainty notes
6. the complete temporary chapter JSON
7. any explicitly supplied video-specific context

Treat the Korean ASR as fallible evidence. Treat the source timestamps as immutable.

## Review order

### 1. Completeness and timing

- Count raw and unique source timestamps.
- Confirm exactly one VTT cue for every unique source timestamp.
- Confirm there are no invented start timestamps.
- Confirm strict order, valid `HH:MM:SS.mmm` formatting, positive durations, next-start-minus-one-millisecond endings, and no overlap.
- Confirm `WEBVTT`, the required blank line, valid UTF-8, and at most two text lines per cue.

Do not continue toward publication if timestamp coverage differs. Repair it first.

### 2. Scene-level conversation logic

Review every conversation continuously, especially phone calls, stories, games, teasing, and member-to-member exchanges.

- Identify scene boundaries and maintain a speaker ledger.
- Check that each question has a coherent response.
- Check subjects, objects, pronouns, and addressees across cue boundaries.
- Look for false speaker changes caused by voice impressions or ASR name substitutions.
- Use later identification to repair earlier ambiguity when justified.
- Correct unnatural literal translations that obscure the actual conversational move.
- Preserve intentional jokes and repetition, but remove pure ASR duplication.

Do not infer a speaker solely from a hobby, catchphrase, or expected personality. These are supporting clues only.

### 3. Relationship-language audit

Inspect every source occurrence of `형`, every English occurrence of `hyung`, and every member-name-plus-`hyung` form.

- Preserve meaningful `hyung`.
- Confirm it points from a younger speaker to an older male addressee.
- Reject `bro`, `brother`, `big brother`, and automatic `Mr.`.
- Correct malformed spellings such as `hung`, `Ye-hyung`, or `Junhyung` when they represent `hyung`.
- Do not add `hyung` merely to label a speaker.

### 4. Terminology audit

- Enforce all canonical names and platforms from the glossary.
- Check romanized wordplay for consistency.
- Ensure context material has not been inserted as unsaid dialogue.
- Do not explain fandom insiders inside subtitles unless the speaker explains them.

### 5. Song and copyright audit

- Locate every musical or lyric passage in the Korean source.
- Remove any reproduced, reconstructed, translated, or transliterated lyrics from the English VTT.
- Preserve every timestamp with a short permitted description.
- Remove guessed song titles.
- Retain clearly non-lyrical comments and reactions.
- Describe conversational lyric quotations without reproducing them.

### 6. ASR uncertainty audit

For each damaged passage:

- compare grammar and likely spacing;
- inspect several cues before and after it;
- check the complete scene logic;
- consult the glossary only as supporting context;
- choose a neutral rendering when evidence remains incomplete.

Add all material uncertainty to the review report with timestamp, Korean source, final English, and a short reason. Never replace uncertainty with invented fluent dialogue.

### 7. Readability audit

- Keep no more than two lines per cue.
- Break lines at natural phrase boundaries.
- Shorten text that cannot realistically be read in its cue duration without losing essential meaning.
- Remove unnecessary explanation and literal Korean clause stacking.
- Use natural international English and consistent punctuation.

### 8. Chapter audit

- Confirm the chapter file is a non-empty JSON list using only `startSeconds` and `title`.
- Confirm every start is a non-negative integer and exactly matches a VTT cue start.
- Confirm starts are strictly increasing and the first chapter begins at the first translated cue.
- Confirm the outline covers the stream through its closing section.
- Merge sections that are too narrow to be useful; do not chapter every short joke or tangent.
- Correct titles that are vague, overly long, unsupported, or based on damaged ASR.
- Remove song lyrics and guessed titles from chapter names.
- Keep established segment or song titles only when the supplied material identifies them reliably.

## Required final validation

Run the repository's deterministic VTT validator. It must verify at minimum:

1. `WEBVTT` header and blank line.
2. Valid UTF-8.
3. Valid start and end timestamps.
4. Strictly increasing starts.
5. Positive cue duration.
6. No overlap.
7. Every source start represented.
8. No additional starts.
9. Duplicate source starts merged.
10. Cue count equals unique source timestamp count.
11. At most two text lines per cue.
12. Terminology lint rejects forbidden `bro`, `brother`, automatic `Mr.`, and malformed `hyung` forms.
13. Chapter JSON structure, ordering, VTT-start matching, first-cue alignment, and title validity.

If validation reports any failure, correct the VTT and rerun it. Do not replace a previously published subtitle file unless the temporary candidate passes every check.

## Review report output

Create a Markdown report containing:

- timestamp and cue counts;
- beginning and end of the file;
- coverage, ordering, overlap, line-count, terminology, and UTF-8 results;
- uncertain passages and conservative decisions;
- important PLAVE terminology and wordplay choices;
- speaker inferences that materially affected dialogue;
- song-handling decisions;
- the validator command and exact result;
- whether the file received human review or automated review only.
- chapter count, first and last chapter, and chapter validation result.

Finish only after the complete corrected VTT, chapter JSON, and review report exist and all validation passes.
