# PLAVE Lives with English Fan Subtitles

A small, static GitHub Pages website that lists only the livestreams shown at
[`@plave_official/streams`](https://www.youtube.com/@plave_official/streams) and plays optional, locally maintained English WebVTT fan subtitles in sync with the embedded YouTube player.

The site uses HTML, CSS, vanilla JavaScript, the YouTube IFrame Player API, and a scheduled GitHub Action. It needs no API key, database, server, account, browser extension, npm installation, or website build step. Videos can optionally include broad, clickable chapter navigation alongside the fan subtitles. A separate **Most replayed** page collects subtitled scenes identified from YouTube's optional replay heatmaps.

## Publish the website for the first time

1. Create a new repository on GitHub.
2. Commit all files in this project and push them to the repository's `main` branch.
3. In the repository, open **Settings → Pages**.
4. Under **Build and deployment**, select **Deploy from a branch**. Choose the `main` branch and the `/ (root)` folder, then click **Save**.
5. Open the GitHub Pages address shown by GitHub. Initial publication can take a few minutes.
6. Open **Actions → Update livestream list → Run workflow** once to populate `data/videos.json`. The Action commits the generated list, and GitHub Pages republishes the changed site automatically.

All browser paths are relative, so this works both for a user/organization Page and for a project Page hosted below `https://USERNAME.github.io/REPOSITORY/`.

If the workflow cannot push, check **Settings → Actions → General → Workflow permissions** and allow read and write permissions for `GITHUB_TOKEN`. The workflow itself requests only `contents: write`, which is required to update the generated JSON files.

## How the livestream list is updated

The workflow runs daily and can also be started at any time from **Actions → Update livestream list → Run workflow**. Scheduled GitHub Actions runs are not guaranteed to start at an exact second and can be delayed during busy periods. It also checks chaptered videos for optional YouTube **Most replayed** heatmap data.

`scripts/update_videos.py` passes only this address to yt-dlp:

```text
https://www.youtube.com/@plave_official/streams
```

It uses flat extraction and does not download videos. Consequently, the site contains only entries exposed by the official channel's **Live** tab—not regular Videos-tab entries, Shorts, or videos from other channels. The script preserves the newest-first order returned by that tab, removes duplicate IDs, and skips private, deleted, unavailable, or malformed entries.

If yt-dlp supplies a reliable upload/release date, it is written as `YYYY-MM-DD`. Flat channel extraction does not always include a date; in that case `publishedAt` is deliberately an empty string and the card omits the date. The YouTube Live-tab order remains the chronology fallback.

The script first writes temporary files and only atomically replaces the JSON data after validation. A temporary YouTube or yt-dlp error therefore does not overwrite an existing non-empty, valid `data/videos.json`. yt-dlp may still need updates if YouTube changes its site; the workflow always installs the current yt-dlp release.

## Add fan subtitles

Suppose the YouTube URL is:

```text
https://www.youtube.com/watch?v=abc123XYZ
```

The video ID is:

```text
abc123XYZ
```

The subtitle file must be named exactly:

```text
subtitles/abc123XYZ.vtt
```

Then:

1. Save the valid WebVTT file in `subtitles/`.
2. Commit and push it to `main`.
3. The push starts the update workflow automatically. Alternatively, start **Update livestream list** manually under **Actions**.
4. After the workflow commits the regenerated `data/subtitles.json` and Pages republishes, confirm that the video's card says **English fan subtitles available**.

Do not edit `data/subtitles.json` manually. It is generated from all validly named `.vtt` files in `subtitles/` on each subtitle push, daily run, and manual run. `subtitles/example.vtt` is neutral placeholder content, is clearly marked as an example, and does not correspond to a PLAVE video.

A minimal subtitle file looks like this:

```vtt
WEBVTT

00:00:01.000 --> 00:00:04.000
Example fan subtitle.

00:00:05.000 --> 00:00:08.000
Replace this file with your own translation.
```

The browser parser supports `MM:SS.mmm`, `HH:MM:SS.mmm`, optional cue IDs, multiline cues, and Windows or Unix line endings. Cue text is inserted with `textContent`, never as unchecked HTML.

## Add chapter navigation

An optional chapter file uses the same YouTube video ID as its filename:

```text
chapters/abc123XYZ.json
```

Example:

```json
[
  {
    "startSeconds": 1,
    "title": "Opening and introductions"
  },
  {
    "startSeconds": 615,
    "title": "Weekend stories"
  }
]
```

Chapter starts are whole seconds, must be strictly increasing, and should match real VTT cue starts. Use broad scene or topic boundaries rather than many tiny sections. Titles should be concise English descriptions supported by the translated conversation.

Save the chapter file together with `subtitles/abc123XYZ.vtt`, then commit and push both files. The update workflow validates all chapter files and regenerates `data/chapters.json`; do not edit that generated manifest manually. A video without a chapter file continues to work normally and simply hides the Chapters section.

### Most replayed chapter badges

The daily workflow also asks yt-dlp for YouTube's optional replay heatmap for every video that has a chapter source file. No video media is downloaded and no API key is used. YouTube does not publish this information through its official public APIs, does not provide it for every video, and may add it only after enough viewing activity has accumulated. A missing heatmap is therefore normal.

When valid heatmap data exists, `scripts/update_heatmaps.py` writes it atomically to `data/heatmaps.json`. A temporary extraction failure or missing response does not erase the last valid heatmap for that video. The website assigns each YouTube heatmap interval to the chapter containing its midpoint. Every chapter containing a normalized heat value of at least `0.5` receives the text badge **🔥 Most replayed**. There is no maximum number of marked chapters: an eventful stream can have many. Videos without heatmap data and chapters below the threshold remain unchanged.

Do not edit `data/heatmaps.json` manually. yt-dlp reads an internal YouTube player representation for this optional feature, so YouTube changes can temporarily break extraction even while normal video and subtitle playback continue to work.

## Most replayed scene page and partial subtitle coverage

`highlights.html` groups subtitled Most replayed scenes by livestream. The date and livestream title are plain headings, not links. Only a scene's timestamp and title form the link that opens the corresponding video at that scene with fan subtitles.

The player passes the scene start to YouTube, seeks to it again when the IFrame API is ready, enables fan subtitles, and attempts to start playback. Safari and iPadOS may still block automatic playback with sound. For that case the page explains that the viewer can tap Play in the YouTube video. A large **Play highlighted scene** button also retries the seek and playback without opening fullscreen. Once YouTube confirms playback, the same control becomes **Restart highlighted scene**.

The generated `data/subtitle-coverage.json` distinguishes two states:

- `full` — the complete VTT is stored at `subtitles/VIDEO_ID.vtt`.
- `highlights` — only declared highlighted scenes are stored at `highlight-subtitles/VIDEO_ID.vtt`.

This prevents a partially translated livestream from being labelled as completely subtitled. Partial scene boundaries are declared in `highlights/VIDEO_ID.json`:

```json
[
  {
    "startSeconds": 615,
    "endSeconds": 842,
    "title": "A complete, understandable scene title"
  }
]
```

Each partial scene must start at a real VTT cue, contain its complete local cue sequence, and end before another undeclared section begins. A cue must never extend across the gap between two translated scenes. If a full `subtitles/VIDEO_ID.vtt` is later added, it automatically takes precedence over the partial file.

`scripts/update_highlights.py` validates the coverage files and generates both `data/subtitle-coverage.json` and `data/highlights.json`. For fully translated streams it maps heatmap peaks to existing broad chapters. For partial translations it uses the deliberately reviewed scene boundaries in `highlights/VIDEO_ID.json`. The same normalized `0.5` threshold used for chapter badges determines whether a scene qualifies. Dates and natural English display titles can be supplied in `metadata/VIDEO_ID.json`.

If a later heatmap no longer places a declared partial scene above the threshold, that scene remains safely stored and subtitled but is temporarily omitted from the Most replayed page. It can reappear automatically if later valid heatmap data qualifies it again.

Do not edit `data/subtitle-coverage.json` or `data/highlights.json` manually. The daily/manual workflow regenerates them after refreshing the video list, chapter manifest, and optional heatmaps.

## Replace or correct subtitles

1. Edit the existing `.vtt` file.
2. Save it under the same video-ID filename.
3. Commit and push the change.
4. Reload the website. If the previous text remains visible, force-refresh Safari or clear the page's cached website data.

Because the filename did not change, the subtitle manifest normally does not need to change. The website requests VTT files with cache revalidation, while GitHub Pages/CDN caching can still take a short time to expire.

## Local preview

Opening `index.html` directly with a `file://` URL can block JSON requests. Use any simple static server instead, for example:

```sh
python3 -m http.server 8000
```

Then open `http://localhost:8000/`. The checked-in `data/videos.json` starts empty; use the GitHub workflow or install yt-dlp locally and run `python3 scripts/update_videos.py` to populate it.

## How playback works

The YouTube IFrame Player API supplies the current playback time every 150 ms. The page selects active VTT cues and safely displays their text both over the embedded video and in a persistent fallback panel below it. Seeking, pausing, resuming, and playback-speed changes work because each poll uses the player's current time rather than a separate clock. If chapter data exists, the page displays large chapter buttons below the player. Optional static heatmap data adds a textual **🔥 Most replayed** badge to every chapter that crosses the documented threshold, without changing chapter order. Selecting a chapter seeks to it, turns on available fan subtitles, starts playback in the normal embedded view, and scrolls the player back into the center of the screen. The centering is repeated after a short delay so Safari cannot immediately undo it while the YouTube iframe starts playback. If Safari still ignores it, a native same-page anchor jump brings the player back into view without adding an extra browser-history entry. Chapter selection never opens fullscreen automatically.

Embedded iframe fullscreen behavior on iPad is controlled by Safari and YouTube, so the normal inline 16:9 player is the primary experience. `playsinline=1` is enabled, and the subtitle panel below the player remains the dependable viewing mode.

## Privacy

The site has no analytics, cookies of its own, or first-party tracking. Livestream thumbnails load only from YouTube's `i.ytimg.com` domain. Loading or playing the embedded player connects the browser to YouTube, which may process data according to Google's/YouTube's policies. YouTube is the only required external service.

## Project files

- `index.html`, `styles.css`, `app.js` — static website and player
- `highlights.html`, `highlights.js` — static Most replayed scene overview
- `data/videos.json` — generated Live-tab video metadata
- `data/subtitles.json` — generated list of available subtitle IDs
- `data/chapters.json` — generated chapter data for the website
- `data/heatmaps.json` — generated optional YouTube replay heatmaps
- `data/subtitle-coverage.json` — generated full/partial subtitle availability
- `data/highlights.json` — generated stream groups and clickable highlighted scenes
- `subtitles/*.vtt` — your English fan subtitle files
- `highlight-subtitles/*.vtt` — optional VTT files covering only declared highlighted scenes
- `chapters/*.json` — optional per-video chapter source files
- `highlights/*.json` — reviewed boundaries and titles for partial subtitle scenes
- `metadata/*.json` — optional dates and natural English display titles
- `scripts/update_videos.py` — yt-dlp metadata and subtitle/chapter-manifest updater
- `scripts/update_heatmaps.py` — optional yt-dlp replay-heatmap updater
- `scripts/update_highlights.py` — coverage validator and static highlight-manifest generator
- `.github/workflows/update-videos.yml` — daily, manual, and subtitle-push automation
