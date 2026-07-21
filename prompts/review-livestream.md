# Task: Review and correct a complete or highlight-only PLAVE livestream translation

Perform a second, independent editorial and technical review of the workflow-selected English VTT coverage for YouTube video `<VIDEO_ID>`. Correct the VTT directly. Do not merely describe problems, and do not stop after spot-checking selected cues.

## Required inputs

Read completely:

1. `docs/subtitle-translation-guide.md`
2. `docs/plave-glossary.md`
3. the structured Korean source for `<VIDEO_ID>`
4. the complete temporary English VTT
5. the translation pass's uncertainty notes
6. the complete temporary `chapters.json` for full mode or `scenes.json` for highlight mode
7. any explicitly supplied video-specific context

Treat the Korean ASR as fallible evidence. Treat the source timestamps as immutable.

## Review order

### 1. Completeness and timing

- Count raw and unique source timestamps.
- For full mode, confirm exactly one VTT cue for every unique source timestamp.
- For highlight mode, confirm exactly one VTT cue for every source timestamp inside the declared scenes, no cues outside them, and end times derived from the complete source.
- Confirm there are no invented start timestamps.
- Confirm strict order, valid `HH:MM:SS.mmm` formatting, positive durations, next-start-minus-one-millisecond endings, and no overlap.
- Confirm `WEBVTT`, the required blank line, valid UTF-8, and at most two text lines per cue.

Do not continue toward publication if timestamp coverage differs. Repair it first.

### 2. Scene-level conversation logic

Review every conversation continuously, especially phone calls, stories, games, teasing, and member-to-member exchanges.

- Identify scene boundaries and maintain a speaker ledger.
- Check that each question has a coherent response.
- Check subjects, objects, pronouns, and addressees across cue boundaries.
- Audit every explicit English `I`, `you`, `we`, `he`, `she`, or member name that was omitted in Korean. Require explicit evidence or several independent scene-level signals.
- Treat pauses and caption boundaries only as supporting evidence, never as proof of a speaker change.
- Replace unsupported assignments with natural neutral wording where possible; otherwise document the narrowest chosen reading and alternatives.
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
- Preserve only a short compact lyric or fan-call excerpt that the user directly supplied and explicitly requested. Confirm the translation does not extend beyond that supplied unit and record the exception in the report.

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
- Review every duration-aware density warning. Shorten ordinary prose; explicitly retain only justified rapid chants, repetitions, names, or sound descriptions.
- Remove unnecessary explanation and literal Korean clause stacking.
- Use natural international English and consistent punctuation.

### 8. Boundary audit

- In full mode, confirm the chapter file is a non-empty JSON list using only `startSeconds` and `title`.
- Confirm every start is a non-negative integer and exactly matches a VTT cue start.
- Confirm starts are strictly increasing and the first chapter begins at the first translated cue.
- Confirm the outline covers the stream through its closing section.
- Merge sections that are too narrow to be useful; do not chapter every short joke or tangent.
- Correct titles that are vague, overly long, unsupported, or based on damaged ASR.
- Remove song lyrics and guessed titles from chapter names.
- Keep established segment or song titles only when the supplied material identifies them reliably.

In highlight mode:

- Confirm `scenes.json` uses exactly `startSeconds`, `endSeconds`, and `title`.
- Confirm scenes are ordered, non-overlapping semantic units and every scene start matches its first VTT cue.
- Confirm each scene contains its intended heatmap peak plus enough setup and immediate resolution.
- Correct automatic padded boundaries that cut through an exchange or include an unrelated activity.
- Confirm every selected cue lies in exactly one scene and no unselected cue appears.

## Required final validation

Run the repository's deterministic VTT validator. It must verify at minimum:

1. `WEBVTT` header and blank line.
2. Valid UTF-8.
3. Valid start and end timestamps.
4. Strictly increasing starts.
5. Positive cue duration.
6. No overlap.
7. Exact source-start coverage for the selected mode.
8. No starts outside the selected full or highlight coverage.
9. Duplicate source starts merged.
10. Cue count equals the expected unique timestamp count for the selected mode.
11. At most two text lines per cue.
12. Terminology lint rejects forbidden `bro`, `brother`, automatic `Mr.`, and malformed `hyung` forms.
13. Chapter JSON structure, ordering, VTT-start matching, first-cue alignment, and title validity.

For highlight mode, replace item 13 with scene structure, semantic boundaries, ordering, non-overlap, complete selected-source coverage, full-source end timing, VTT-start matching, and title validity.

If validation reports any failure, correct the VTT and rerun it. Do not replace a previously published subtitle file unless the temporary candidate passes every check.

If the translation used parallel scene work, the review must additionally read every merged boundary sequentially with cues on both sides. Confirm that speaker identity, addressee, pronouns, topic, jokes, and terminology remain continuous. Parallel scene completion is not a substitute for this unified final pass.

Keep machine-generated validation summaries separate from editorial notes, or merge without overwriting reviewed uncertainty, wordplay, speaker, and lyric decisions. After validation succeeds, run the local finalization step to seal the exact reviewed files. Stop at `ready_for_publication_approval`; publication requires a new explicit user approval.

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
- for full mode: chapter count, first and last chapter, and chapter validation result;
- for highlight mode: scene count, boundaries, titles, heatmap containment, and partial-coverage validation result.

Finish only after the corrected VTT, mode-appropriate boundary JSON, and review report exist and all validation passes.
