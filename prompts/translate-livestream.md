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
7. For damaged ASR, check grammar, surrounding questions and answers, repeated expressions, and the glossary. Use the narrowest supported interpretation.
8. Record every material uncertainty instead of silently inventing a polished answer.
9. Save progress regularly to the temporary output, while retaining complete timestamp coverage.
10. Recount timestamps after each major section.
11. Record broad scene boundaries while translating, then turn them into the chapter JSON draft.

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
