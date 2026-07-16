# PLAVE Lives with English Fan Subtitles

A small, static GitHub Pages website that lists only the livestreams shown at
[`@plave_official/streams`](https://www.youtube.com/@plave_official/streams) and plays optional, locally maintained English WebVTT fan subtitles in sync with the embedded YouTube player.

The site uses HTML, CSS, vanilla JavaScript, the YouTube IFrame Player API, and a scheduled GitHub Action. It needs no API key, database, server, account, browser extension, npm installation, or website build step.

## Publish the website for the first time

1. Create a new repository on GitHub.
2. Commit all files in this project and push them to the repository's `main` branch.
3. In the repository, open **Settings → Pages**.
4. Under **Build and deployment**, select **Deploy from a branch**. Choose the `main` branch and the `/ (root)` folder, then click **Save**.
5. Open the GitHub Pages address shown by GitHub. Initial publication can take a few minutes.
6. Open **Actions → Update livestream list → Run workflow** once to populate `data/videos.json`. The Action commits the generated list, and GitHub Pages republishes the changed site automatically.

All browser paths are relative, so this works both for a user/organization Page and for a project Page hosted below `https://USERNAME.github.io/REPOSITORY/`.

If the workflow cannot push, check **Settings → Actions → General → Workflow permissions** and allow read and write permissions for `GITHUB_TOKEN`. The workflow itself requests only `contents: write`, which is required to update the two generated JSON files.

## How the livestream list is updated

The workflow runs daily and can also be started at any time from **Actions → Update livestream list → Run workflow**. Scheduled GitHub Actions runs are not guaranteed to start at an exact second and can be delayed during busy periods.

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

The YouTube IFrame Player API supplies the current playback time every 150 ms. The page selects active VTT cues and safely displays their text both over the embedded video and in a persistent fallback panel below it. Seeking, pausing, resuming, and playback-speed changes work because each poll uses the player's current time rather than a separate clock.

Embedded iframe fullscreen behavior on iPad is controlled by Safari and YouTube, so the normal inline 16:9 player is the primary experience. `playsinline=1` is enabled, and the subtitle panel below the player remains the dependable viewing mode.

## Privacy

The site has no analytics, cookies of its own, or first-party tracking. Livestream thumbnails load only from YouTube's `i.ytimg.com` domain. Loading or playing the embedded player connects the browser to YouTube, which may process data according to Google's/YouTube's policies. YouTube is the only required external service.

## Project files

- `index.html`, `styles.css`, `app.js` — static website and player
- `data/videos.json` — generated Live-tab video metadata
- `data/subtitles.json` — generated list of available subtitle IDs
- `subtitles/*.vtt` — your English fan subtitle files
- `scripts/update_videos.py` — yt-dlp metadata and subtitle-manifest updater
- `.github/workflows/update-videos.yml` — daily, manual, and subtitle-push automation
