# Task: Translate a complete PLAVE livestream or selected highlight scenes into English WebVTT

Translate the workflow-selected coverage for YouTube video `<VIDEO_ID>` into natural English fan subtitles. For `full` mode, process the complete source. For `highlights` mode, process every approved scene completely. Do not stop after a sample or an incomplete selected scene.

## Required references

Read these files completely before translating:

1. `docs/subtitle-translation-guide.md`
2. `docs/plave-glossary.md`
3. the structured Korean source supplied for `<VIDEO_ID>`
4. any video-specific metadata or trusted context files explicitly supplied by the workflow

The translation guide and glossary are binding. Video-specific context may clarify a scene but must never be inserted as dialogue.

## Output contract

Create:

- the English VTT at the workflow-provided temporary output path;
- in `full` mode, a complete chapter JSON draft at the workflow-provided temporary chapter path;
- in `highlights` mode, a complete scene JSON at the workflow-provided temporary scene path;
- structured uncertainty notes at the workflow-provided review-notes path.

Do not modify the downloaded source. Do not publish or commit files yourself.

## Hard requirements

- In `full` mode, represent every unique source start timestamp exactly once.
- In `highlights` mode, represent every source start inside every approved scene exactly once and no source starts outside those scenes.
- Do not add, remove, shift, round, or reorder start timestamps.
- Merge duplicate source timestamps before translation, preserving source order.
- Set every cue end to the next start minus one millisecond; give only the final cue a short positive duration.
- Begin with `WEBVTT` and a blank line.
- Use at most two text lines per cue and no HTML or WebVTT styling.
- Translate Korean speech faithfully, naturally, and concisely.
- Never translate `형` as `bro`, `brother`, `big brother`, or `Mr.`. Use `hyung` where relationally relevant.
- Use canonical PLAVE names and terminology from the glossary.
- Do not reproduce, reconstruct, transliterate, or translate song lyrics. Preserve all lyric timestamps with brief descriptions.
- If the user directly supplied and explicitly requested translation of a short compact lyric or fan-call excerpt, translate only that exact supplied unit. Do not extend the exception into adjacent captions or a longer performance.
- Do not invent speakers, dialogue, jokes, objects, titles, or explanations.

## Working method

1. Parse and count all raw and unique source timestamps programmatically.
2. Create a structured intermediate cue list.
3. Mark likely music/lyric ranges before prose translation.
4. Divide the source into coherent scenes, not arbitrary isolated cues.
5. Translate scenes sequentially with contextual overlap at section boundaries.
6. Maintain a scene ledger for speakers, addressees, topic, relationship terms, and unresolved turns.
7. Mark every restored omitted subject, object, or addressee as confirmed, strongly supported, or unclear. Do not use pauses or caption boundaries as sufficient speaker evidence.
8. For damaged ASR, check grammar, surrounding questions and answers, repeated expressions, and the glossary. Use the narrowest supported interpretation.
9. Record every material uncertainty instead of silently inventing a polished answer.
10. Save progress regularly to the temporary output, while retaining complete timestamp coverage.
11. Recount timestamps after each major section.
12. Record broad scene boundaries while translating, then turn them into the chapter JSON draft.

For highlight mode, treat the automated heatmap plan only as discovery input. Read wider context around each peak and replace padded boundaries with complete semantic scenes containing setup, popular moment, and immediate resolution. Do not cut through an exchange or absorb an unrelated later activity.

For resumable scene work, use compact per-scene JSON containing `scene`, `title`, `startSeconds`, `endBoundarySeconds`, timestamp-complete `cues` pairs shaped as `[startSeconds, translation]`, `uncertainties`, and `speakerNotes`. Save long scenes in small progress chunks. Generated assembly summaries must not overwrite final editorial notes.

Clearly independent scenes may be translated in parallel only after their boundaries have been contextually reviewed. Do not parallelize adjacent parts of one call, story, game, joke, role-play, or unresolved speaker exchange. Give every parallel scene the same glossary and known-speaker ledger, preserve contextual overlap, and return its uncertainty notes. After merging in source order, perform a single sequential pass across all scene boundaries. When independence is doubtful, keep the scenes sequential.

Use only the already prepared work-directory inputs during translation. Do not publish, commit, push, or make repeated network requests. Save resumable progress locally so the user does not need to supervise the long-running phase.

## Chapter draft

Create a concise navigation outline for the entire livestream:

- use `[{"startSeconds": 0, "title": "..."}]` structure;
- use only integer start seconds that exactly match an existing source/VTT cue start;
- make the first chapter start at the first translated cue;
- keep starts strictly increasing;
- cover the whole livestream through its closing section;
- use broad, meaningful segments rather than a chapter for every short tangent;
- for a typical two-hour conversational stream, aim for roughly 10–20 chapters when the content supports them;
- write natural, compact English titles based only on translated content;
- do not place lyrics, uncertain proper names, or invented explanations in titles.

In highlight mode, replace the chapter draft with `scenes.json`:

- use `[{"startSeconds": 123, "endSeconds": 456, "title": "..."}]`;
- make `startSeconds` the first selected source/VTT cue and `endSeconds` the exclusive semantic boundary;
- keep scenes ordered, non-overlapping, and complete;
- ensure every selected cue lies in exactly one scene;
- use a concise recognizable title supported by the scene;
- keep the Most replayed peak inside the scene without treating heatmap padding as the final boundary.

## Conversation standard

For calls, stories, games, and extended jokes, read and translate the full scene as one conversation. Verify that:

- questions and answers logically connect;
- omitted subjects are restored consistently;
- explicit English pronouns are backed by confirmed or multiple strongly supporting scene signals;
- pronouns and member names do not switch without evidence;
- voice impressions are not mistaken for speaker changes;
- `hyung` points in the correct relationship direction;
- humor and teasing remain recognizable without invented explanations.

If the ASR names an implausible subject but adjacent dialogue clearly establishes another, make only the minimum correction required for coherence and document it.

## Song handling

Replace lyric-only material with descriptions such as:

- `[Bamby sings]`
- `[Singing]`
- `[Bamby sings in English]`
- `[Bamby sings in Japanese]`
- `[Music]`

Use a song title only when it is explicitly and reliably established by supplied material. Translate non-lyrical comments, laughter, and interruptions normally.

The only lyric exception is a short compact excerpt directly supplied by the user and explicitly requested for translation. Record that exact excerpt in the review notes; surrounding lyrics remain descriptions.

## Completion check

Before finishing, verify programmatically that the temporary VTT has exact timestamp coverage for the selected mode and no additional starts. For full mode, validate chapters; for highlight mode, validate scene coverage against the complete-source timing. Run duration-aware density warnings and shorten unjustified dense cues. Then hand the VTT, boundary draft, and uncertainty notes to the separate review pass. Do not claim success if any required section or timestamp is missing.
