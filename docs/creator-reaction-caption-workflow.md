# Creator reaction captions: audio and on-screen context

1. Align the available Korean captions and a local audio transcription to the uncut VOD. Use audio from the start. Treat Korean ASR and OCR as evidence, not authoritative text.
2. For visible chat and notes, crop those regions separately from a local copy or recording. Run Korean OCR locally (Apple Vision on macOS) across the whole chosen interval, initially every two seconds. Keep timestamps, merge near-duplicates across adjacent frames, and reconstruct wrapped lines. Verify the offset against a visible clock or distinct source anchors; use VOD times in the VTT. If the platform or creator provides the actual chat log as text, prefer that for the messages it covers.
3. Pass only new, timestamped text with short adjacent transcript excerpts to translation and editorial review. Inspect cropped images only when the wording, speaker, or visual joke is uncertain. Rescan at 0.5–1 second for fast chat or Short captions; reuse OCR results when revising subtitles.
4. Mark chat a streamer reads as `[Reading chat]`; use `[Chat: …]` for unspoken comments and `[On screen: …]` or `[Caption: …]` for visual text. Preserve surprise/question intonation from audio. Select reactions that explain a joke, a prediction that lands or misses, or an otherwise unclear referent. Do not translate the whole chat feed.
5. Watch the bounded draft in the same player before publishing. Validate WebVTT ordering, bounds, and readability. A single guest VTT uses the original YouTube ID and may cover multiple non-overlapping excerpts. The original entry retains its `?v=VIDEO_ID` URL; an additional entry sets an `excerpt` slug and uses `?v=VIDEO_ID&excerpt=SLUG`. Preserve existing excerpts and skips. Do not commit source captions, OCR dumps, frames, or recordings.

This worked for the SOLF excerpt at 26:00–1:07:55: 1,258 local frame samples made context recoverable without sending the full image series to a generative model. The remaining savings come from filtering and aligning OCR output locally before translation.

## Creator reactions catalogue

`creator-reactions.html` groups the reviewed excerpt entries by YouTube ID,
showing one card per video. For the video detail view,
`data/guest-chapters.json` stores the source duration in seconds and the
uploader's chapter start times with reviewed English titles. You can obtain
the source boundaries without downloading media:
`yt-dlp --skip-download --no-playlist --print "%(chapters)j" URL`.
Keep chapter boundaries separate from the reviewed coverage intervals in
`data/guest-videos.json`. The player merges touching coverage intervals,
preserves approved skips, and does not use gaps between normal subtitle cues
to decide where to stop.
