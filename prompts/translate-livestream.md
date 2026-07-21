# Task: Translate a complete PLAVE livestream into English WebVTT

Translate the complete Korean source for YouTube video `<VIDEO_ID>` into natural English fan subtitles. Work through the entire source; do not stop after a sample or partial draft.

## Required references

Read these files completely before translating:

1. `docs/subtitle-translation-guide.md`
2. `docs/plave-glossary.md`
3. the structured Korean source supplied for `<VIDEO_ID>`
4. any video-specific metadata or trusted context files explicitly supplied by the workflow

The translation guide and glossary are binding. Video-specific context may clarify a scene but must never be inserted as dialogue.

## Output contract

Create:

- the complete English VTT at the workflow-provided temporary output path;
- a complete chapter JSON draft at the workflow-provided temporary chapter path;
- structured uncertainty notes at the workflow-provided review-notes path.

Do not modify the downloaded source. Do not publish or commit files yourself.

## Hard requirements

- Represent every unique source start timestamp exactly once.
- Do not add, remove, shift, round, or reorder start timestamps.
- Merge duplicate source timestamps before translation, preserving source order.
- Set every cue end to the next start minus one millisecond; give only the final cue a short positive duration.
- Begin with `WEBVTT` and a blank line.
- Use at most two text lines per cue and no HTML or WebVTT styling.
- Translate Korean speech faithfully, naturally, and concisely.
- Never translate `형` as `bro`, `brother`, `big brother`, or `Mr.`. Use `hyung` where relationally relevant.
- Use canonical PLAVE names and terminology from the glossary.
- Do not reproduce, reconstruct, transliterate, or translate song lyrics. Preserve all lyric timestamps with brief descriptions.
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

## Completion check

Before finishing, verify programmatically that the temporary VTT contains the same unique start timestamps as the source and no additional ones. Confirm that every chapter start exists in the VTT and that the chapter list is strictly increasing. Then hand the complete VTT, chapter draft, and uncertainty notes to the separate review pass. Do not claim success if any section or timestamp is missing.
