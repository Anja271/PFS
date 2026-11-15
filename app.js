(function () {
  "use strict";

  const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{6,20}$/;
  const POLL_INTERVAL_MS = 150;
  const HOT_CHAPTER_THRESHOLD = 0.5;
  const state = {
    videos: [],
    guests: new Map(),
    guestChapters: new Map(),
    officialListLoaded: false,
    subtitleIds: new Set(),
    subtitleManifestLoaded: false,
    subtitleCoverage: new Map(),
    coverageManifestLoaded: false,
    chaptersByVideo: new Map(),
    heatmapsByVideo: new Map(),
    currentChapters: [],
    selectedVideo: null,
    player: null,
    playerReady: false,
    cues: [],
    subtitlesEnabled: false,
    activeCueKey: null,
    pollTimer: null,
    initialStartSeconds: 0,
    initialEndSeconds: 0,
    nextSkip: 0,
    highlightEnded: false,
    returnToHighlights: false
  };

  const elements = {
    listView: document.getElementById("list-view"),

    playerView: document.getElementById("player-view"),
    videoGrid: document.getElementById("video-grid"),
    listMessage: document.getElementById("list-message"),
    filter: document.getElementById("video-filter"),
    playerTitle: document.getElementById("player-title"),
    playerStatus: document.getElementById("player-status"),
    playerMessage: document.getElementById("player-message"),
    highlightStart: document.getElementById("highlight-start"),
    subtitleToggle: document.getElementById("subtitle-toggle"),
    fullscreenToggle: document.getElementById("fullscreen-toggle"),
    playerFrame: document.getElementById("player-frame"),
    chapterSection: document.getElementById("chapter-section"),
    chapterList: document.getElementById("chapter-list"),
    subtitleOverlay: document.getElementById("subtitle-overlay"),
    subtitleFallback: document.getElementById("subtitle-fallback"),
    youtubeLink: document.getElementById("youtube-link"),
    backLink: document.getElementById("back-link")
  };

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    const creatorPage = document.getElementById("creator-page");
    if (creatorPage) {
      await renderCreatorPage(creatorPage);
      return;
    }
    elements.filter.addEventListener("change", renderVideoList);
    elements.subtitleToggle.addEventListener("click", toggleSubtitles);
    elements.fullscreenToggle.addEventListener("click", togglePlayerFullscreen);
    elements.backLink.addEventListener("click", handleBackLink);
    document.addEventListener("fullscreenchange", updateFullscreenButton);
    window.addEventListener("popstate", route);

    const [videosResult, subtitlesResult, coverageResult, chaptersResult, heatmapsResult, guestsResult, guestChaptersResult] = await Promise.allSettled([
      fetchJson("data/videos.json"),
      fetchJson("data/subtitles.json"),
      fetchJson("data/subtitle-coverage.json"),
      fetchJson("data/chapters.json"),
      fetchJson("data/heatmaps.json"),
      fetchJson("data/guest-videos.json"),
      fetchJson("data/guest-chapters.json")
    ]);

    if (videosResult.status === "fulfilled" && Array.isArray(videosResult.value)) {
      state.videos = videosResult.value.filter(isValidVideo);
      state.officialListLoaded = true;
    }

    if (subtitlesResult.status === "fulfilled" && Array.isArray(subtitlesResult.value)) {
      state.subtitleIds = new Set(subtitlesResult.value.filter(isValidVideoId));
      state.subtitleManifestLoaded = true;
    } else {
      state.subtitleManifestLoaded = false;
    }

    if (coverageResult.status === "fulfilled") {
      state.subtitleCoverage = normalizeCoverageManifest(coverageResult.value);
      state.coverageManifestLoaded = true;
    } else {
      state.coverageManifestLoaded = false;
    }

    if (chaptersResult.status === "fulfilled") {
      state.chaptersByVideo = normalizeChapterManifest(chaptersResult.value);
    }

    if (heatmapsResult.status === "fulfilled") {
      state.heatmapsByVideo = normalizeHeatmapManifest(heatmapsResult.value);
    }

    if (guestsResult.status === "fulfilled") {
      state.guests = normalizeGuestVideos(guestsResult.value, state.videos);
    }
    if (guestChaptersResult.status === "fulfilled") {
      state.guestChapters = normalizeGuestChapters(guestChaptersResult.value);
    }
    renderVideoList();
    route();
  }

  async function fetchJson(path) {
    const response = await fetch(path, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
  }

  function isValidVideoId(value) {
    return typeof value === "string" && VIDEO_ID_PATTERN.test(value);
  }

  function isValidVideo(video) {
    return Boolean(video && isValidVideoId(video.youtubeId) && typeof video.title === "string");
  }

  function normalizeGuestVideos(value, officialVideos) {
    const guests = new Map();
    if (!Array.isArray(value)) return guests;
    const officialIds = new Set(officialVideos.map((video) => video.youtubeId));
    for (const item of value) {
      if (!isValidVideo(item) || officialIds.has(item.youtubeId)) continue;
      const { youtubeId, startSeconds, endSeconds } = item;
      if (!Number.isSafeInteger(startSeconds) || startSeconds < 0
        || !Number.isSafeInteger(endSeconds) || endSeconds <= startSeconds) continue;
      const title = item.title.trim();
      const creator = typeof item.creator === "string" ? item.creator.trim() : "";
      const excerpt = item.excerpt ?? "";
      if (!title || !creator || typeof excerpt !== "string"
        || (excerpt && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(excerpt))) continue;
      const guest = guests.get(youtubeId);
      if (guest?.excerpts.some((entry) => entry.excerpt === excerpt)) continue;
      const skip = item.skip;
      const skips = Number.isFinite(skip?.from) && Number.isFinite(skip?.to)
        && startSeconds < skip.from && skip.from < skip.to && skip.to < endSeconds
        ? [{ from: skip.from, to: skip.to }] : [];
      const entry = { youtubeId, title, creator, excerpt, startSeconds, endSeconds, skips };
      if (guest) {
        guest.excerpts.push(entry);
        if (!excerpt) Object.assign(guest, entry);
      } else {
        guests.set(youtubeId, { ...entry, excerpts: [entry] });
      }
    }
    for (const guest of guests.values()) guest.ranges = mergeGuestRanges(guest.excerpts);
    return guests;
  }

  function mergeGuestRanges(excerpts) {
    const merged = [];
    for (const item of [...excerpts].sort((a, b) => a.startSeconds - b.startSeconds)) {
      const prior = merged.at(-1);
      if (prior && item.startSeconds <= prior.endSeconds) {
        prior.endSeconds = Math.max(prior.endSeconds, item.endSeconds);
        prior.skips.push(...item.skips);
      } else {
        merged.push({ startSeconds: item.startSeconds, endSeconds: item.endSeconds, skips: [...item.skips] });
      }
    }
    return merged;
  }

  function normalizeGuestChapters(value) {
    const result = new Map();
    if (!value || typeof value !== "object") return result;
    for (const [id, item] of Object.entries(value)) {
      if (!isValidVideoId(id) || !Number.isSafeInteger(item?.durationSeconds) || item.durationSeconds <= 0) continue;
      const chapters = normalizeChapterManifest({ [id]: item.chapters }).get(id) || [];
      const bounded = chapters.filter((chapter) => chapter.startSeconds < item.durationSeconds);
      result.set(id, bounded.map((chapter, i) => ({
        ...chapter, endSeconds: bounded[i + 1]?.startSeconds ?? item.durationSeconds
      })));
    }
    return result;
  }

  function guestChapterRuns(guest, chapter) {
    return guest.ranges
      .filter((range) => range.startSeconds < chapter.endSeconds && chapter.startSeconds < range.endSeconds)
      .map((range) => {
        let startSeconds = Math.max(range.startSeconds, chapter.startSeconds);
        for (const skip of range.skips) {
          if (startSeconds >= skip.from && startSeconds < skip.to) startSeconds = Math.ceil(skip.to);
        }
        return { ...range, startSeconds };
      })
      .filter((range) => range.startSeconds < Math.min(range.endSeconds, chapter.endSeconds));
  }

  function guestChapterUrl(id, chapter, run) {
    return `./?v=${encodeURIComponent(id)}&chapter=${chapter.startSeconds}&t=${run.startSeconds}`;
  }

  function guestDetailUrl(id) {
    return `creator-reactions.html?v=${encodeURIComponent(id)}`;
  }

  async function renderCreatorPage(page) {
    const id = new URLSearchParams(window.location.search).get("v");
    const message = document.getElementById("creator-message");
    let guests;
    try {
      guests = normalizeGuestVideos(await fetchJson("data/guest-videos.json"), []);
    } catch {
      showMessage(message, "Creator reactions could not be loaded. Reload this page to try again.", true);
      return;
    }
    if (!id) {
      if (!guests.size) {
        showMessage(message, "No creator reactions have been added yet.", false);
        return;
      }
      page.querySelector("#creator-grid").replaceChildren(...Array.from(guests.values(), createCreatorCard));
      message.hidden = true;
      return;
    }
    const guest = guests.get(id);
    if (!guest) {
      showMessage(message, "This video is not listed. Return to Creator reactions to choose a video.", true);
      return;
    }
    document.title = `${guest.title} — Creator reactions`;
    document.getElementById("creator-back").hidden = false;
    document.getElementById("creator-title").textContent = guest.title;
    let chapters;
    try {
      chapters = normalizeGuestChapters(await fetchJson("data/guest-chapters.json")).get(id) || [];
    } catch {
      showMessage(message, "YouTube chapters could not be loaded. The subtitled excerpts are still available below.", true);
    }
    if (!chapters?.length) {
      if (chapters) showMessage(message, "No YouTube chapters are listed for this video. Choose a subtitled excerpt below.", false);
      page.querySelector("#creator-grid").replaceChildren(...guest.excerpts.map(createCreatorCard));
      return;
    }
    page.querySelector("#creator-intro").textContent =
      "Watch a subtitled chapter here; playback continues into the next chapter while subtitles are available.";
    const list = document.getElementById("creator-chapters");
    list.replaceChildren(...chapters.map((chapter) => createCreatorChapter(guest, chapter)));
    list.hidden = false;
    message.hidden = true;
  }

  function createCreatorCard(video) {
    const card = document.createElement("article");
    card.className = "video-card";
    const content = document.createElement("div");
    content.className = "card-content";
    const heading = document.createElement("h3");
    heading.className = "video-title";
    const link = document.createElement("a");
    link.className = "creator-title-link";
    link.href = video.excerpts ? guestDetailUrl(video.youtubeId)
      : `./?v=${encodeURIComponent(video.youtubeId)}${video.excerpt ? `&excerpt=${encodeURIComponent(video.excerpt)}` : ""}`;
    link.textContent = video.title;
    const detail = document.createElement("p");
    detail.className = "video-date";
    detail.textContent = video.excerpts ? video.creator
      : `${formatChapterTime(video.startSeconds)}–${formatChapterTime(video.endSeconds)}`;
    heading.appendChild(link);
    content.append(heading, detail);
    card.appendChild(content);
    return card;
  }

  function createCreatorChapter(guest, chapter) {
    const item = document.createElement("li");
    const runs = guestChapterRuns(guest, chapter);
    const fullyCovered = runs.length === 1 && runs[0].startSeconds === chapter.startSeconds
      && runs[0].endSeconds >= chapter.endSeconds
      && !runs[0].skips.some((skip) => skip.from < chapter.endSeconds && skip.to > chapter.startSeconds);
    const link = document.createElement("a");
    link.className = "card-segment-link creator-chapter-link";
    link.href = runs.length ? guestChapterUrl(guest.youtubeId, chapter, runs[0])
      : `https://www.youtube.com/watch?v=${encodeURIComponent(guest.youtubeId)}&t=${chapter.startSeconds}s`;
    const title = document.createElement("span");
    title.className = "card-segment-title";
    title.textContent = chapter.title;
    const time = document.createElement("span");
    time.className = "card-segment-time";
    time.textContent = formatChapterTime(chapter.startSeconds);
    const status = document.createElement("span");
    status.className = `subtitle-status ${runs.length ? "status-available" : "status-missing"}`;
    status.textContent = fullyCovered ? "English subtitles"
      : runs.length ? `Partial English subtitles · from ${formatChapterTime(runs[0].startSeconds)}`
        : "No fan subtitles · YouTube";
    link.append(title, time, status);
    item.appendChild(link);
    for (const run of runs.slice(1)) {
      const extra = document.createElement("a");
      extra.className = "creator-title-link";
      extra.href = guestChapterUrl(guest.youtubeId, chapter, run);
      extra.textContent = `Also subtitled from ${formatChapterTime(run.startSeconds)}`;
      item.appendChild(extra);
    }
    return item;
  }

  function normalizeChapterManifest(value) {
    const manifest = new Map();
    if (!value || typeof value !== "object" || Array.isArray(value)) return manifest;
    Object.entries(value).forEach(([videoId, chapters]) => {
      if (!isValidVideoId(videoId) || !Array.isArray(chapters)) return;
      const normalized = [];
      let previousStart = -1;
      for (const chapter of chapters) {
        if (!chapter || typeof chapter !== "object") return;
        const startSeconds = chapter.startSeconds;
        const title = typeof chapter.title === "string" ? chapter.title.trim() : "";
        if (
          !Number.isInteger(startSeconds)
          || startSeconds < 0
          || startSeconds <= previousStart
          || !title
          || title.length > 120
        ) return;
        normalized.push({ startSeconds, title });
        previousStart = startSeconds;
      }
      if (normalized.length) manifest.set(videoId, normalized);
    });
    return manifest;
  }

  function normalizeCoverageManifest(value) {
    const manifest = new Map();
    if (!value || typeof value !== "object" || Array.isArray(value)) return manifest;
    Object.entries(value).forEach(([videoId, entry]) => {
      if (!isValidVideoId(videoId) || !entry || typeof entry !== "object") return;
      if (entry.coverage !== "full" && entry.coverage !== "highlights") return;
      const ranges = [];
      let previousEnd = -1;
      if (!Array.isArray(entry.ranges)) return;
      for (const range of entry.ranges) {
        if (
          !range
          || !Number.isInteger(range.startSeconds)
          || !Number.isInteger(range.endSeconds)
          || range.startSeconds < 0
          || range.endSeconds <= range.startSeconds
          || range.startSeconds < previousEnd
        ) return;
        ranges.push({ startSeconds: range.startSeconds, endSeconds: range.endSeconds });
        previousEnd = range.endSeconds;
      }
      if (entry.coverage === "full" && ranges.length) return;
      if (entry.coverage === "highlights" && !ranges.length) return;
      manifest.set(videoId, { coverage: entry.coverage, ranges });
    });
    return manifest;
  }

  function normalizeHeatmapManifest(value) {
    const manifest = new Map();
    if (!value || typeof value !== "object" || Array.isArray(value)) return manifest;
    Object.entries(value).forEach(([videoId, points]) => {
      if (!isValidVideoId(videoId) || !Array.isArray(points) || !points.length) return;
      const normalized = [];
      let previousStart = -1;
      for (const point of points) {
        if (!point || typeof point !== "object") return;
        const startSeconds = point.startSeconds;
        const endSeconds = point.endSeconds;
        const heat = point.value;
        if (
          !Number.isFinite(startSeconds)
          || !Number.isFinite(endSeconds)
          || !Number.isFinite(heat)
          || startSeconds < 0
          || endSeconds <= startSeconds
          || startSeconds <= previousStart
          || heat < 0
          || heat > 1
        ) return;
        normalized.push({ startSeconds, endSeconds, value: heat });
        previousStart = startSeconds;
      }
      manifest.set(videoId, normalized);
    });
    return manifest;
  }

  function renderVideoList() {
    elements.videoGrid.replaceChildren();
    const onlySubtitled = elements.filter.value === "subtitled";
    const videos = onlySubtitled
      ? state.videos.filter((video) => hasAnySubtitles(video.youtubeId))
      : state.videos;

    if (!state.officialListLoaded) {
      showMessage(elements.listMessage, "The livestream list could not be loaded. Please try again later.", true);
    } else if (!state.subtitleManifestLoaded && !state.coverageManifestLoaded) {
      showMessage(elements.listMessage, "Subtitle availability could not be loaded. Livestreams are still available to watch.", true);
    } else if (videos.length === 0) {
      showMessage(
        elements.listMessage,
        onlySubtitled ? "No livestreams with fan subtitles are available yet." : "No livestreams are available yet.",
        false
      );
    } else {
      elements.listMessage.hidden = true;
    }

    const fragment = document.createDocumentFragment();
    videos.forEach((video) => fragment.appendChild(createVideoCard(video)));
    elements.videoGrid.appendChild(fragment);
  }

  function createVideoCard(video) {
    const article = document.createElement("article");
    article.className = "video-card";

    const thumbnailWrap = document.createElement("div");
    thumbnailWrap.className = "thumbnail-wrap";
    const image = document.createElement("img");
    // Derive the URL from the validated ID so manually edited JSON cannot load
    // images or tracking pixels from non-YouTube hosts.
    image.src = `https://i.ytimg.com/vi/${video.youtubeId}/hqdefault.jpg`;
    image.alt = "";
    image.loading = "lazy";
    image.width = 480;
    image.height = 270;
    thumbnailWrap.appendChild(image);

    const content = document.createElement("div");
    content.className = "card-content";
    const title = document.createElement("h3");
    title.className = "video-title";
    title.textContent = video.title;
    content.appendChild(title);

    if (video.creator || video.publishedAt) {
      const date = document.createElement("p");
      date.className = "video-date";
      date.textContent = video.creator
        ? `${video.creator} · ${formatChapterTime(video.startSeconds)}–${formatChapterTime(video.endSeconds)}`
        : formatDate(video.publishedAt);
      content.appendChild(date);
    }

    content.appendChild(createStatus(video.youtubeId));

    const watch = document.createElement("a");
    watch.className = "button button-primary";
    watch.href = `?v=${encodeURIComponent(video.youtubeId)}`;
    if (video.excerpt) watch.href += `&excerpt=${encodeURIComponent(video.excerpt)}`;
    watch.textContent = video.creator ? "Watch subtitled excerpt" : "Watch";
    watch.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      history.pushState({ fromList: true }, "", watch.href);
      route();
    });
    content.appendChild(watch);

    article.append(thumbnailWrap, content);
    return article;
  }

  function createStatus(videoId) {
    const status = document.createElement("p");
    status.className = "subtitle-status";
    setStatus(status, videoId);
    return status;
  }

  function setStatus(element, videoId) {
    element.className = "subtitle-status";
    const coverage = getSubtitleCoverage(videoId);
    if (coverage === "guest") {
      element.textContent = "English fan subtitles for this excerpt";
      element.classList.add("status-available");
    } else if (!state.subtitleManifestLoaded && !state.coverageManifestLoaded) {
      element.textContent = "Fan subtitle status unknown";
      element.classList.add("status-unknown");
    } else if (coverage === "full") {
      element.textContent = "English fan subtitles available";
      element.classList.add("status-available");
    } else if (coverage === "highlights") {
      element.textContent = "English subtitles available for highlighted scenes";
      element.classList.add("status-highlight");
    } else {
      element.textContent = "No fan subtitles yet";
      element.classList.add("status-missing");
    }
  }

  function getSubtitleCoverage(videoId) {
    if (state.guests.has(videoId)) return "guest";
    const entry = state.subtitleCoverage.get(videoId);
    if (entry) return entry.coverage;
    return state.subtitleIds.has(videoId) ? "full" : null;
  }

  function hasAnySubtitles(videoId) {
    return getSubtitleCoverage(videoId) !== null;
  }

  function formatDate(dateString) {
    const date = new Date(`${dateString}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) return dateString;
    return new Intl.DateTimeFormat("en", {
      year: "numeric", month: "long", day: "numeric", timeZone: "UTC"
    }).format(date);
  }

  function route() {
    const params = new URLSearchParams(window.location.search);
    const requestedId = params.get("v");
    if (!requestedId) {
      showListView();
      return;
    }
    if (!isValidVideoId(requestedId)) {
      showListView();
      showMessage(elements.listMessage, "The video ID in the address is invalid. Choose a livestream below.", true);
      return;
    }
    const guest = state.guests.get(requestedId);
    const video = guest || state.videos.find((item) => item.youtubeId === requestedId);
    if (!video) {
      showListView();
      showMessage(elements.listMessage, "This video is not listed in the guide. Choose a video below.", true);
      return;
    }
    if (guest) {
      if (params.has("chapter")) {
        const chapter = state.guestChapters.get(requestedId)?.find(
          (item) => String(item.startSeconds) === params.get("chapter"));
        const run = chapter && guestChapterRuns(guest, chapter).find(
          (item) => String(item.startSeconds) === params.get("t"));
        if (run) {
          showPlayerView({ ...guest, ...run }, run.startSeconds, false, run.endSeconds);
        } else {
          window.location.href = guestDetailUrl(requestedId);
        }
        return;
      }
      const excerpt = params.get("excerpt") ?? "";
      const entry = guest.excerpts.find((item) => item.excerpt === excerpt);
      if (!entry) {
        window.location.href = guestDetailUrl(requestedId);
        return;
      }
      const range = guest.ranges.find((item) => item.startSeconds <= entry.startSeconds
        && item.endSeconds >= entry.endSeconds);
      showPlayerView({ ...entry, skips: range.skips }, entry.startSeconds, false, range.endSeconds);
      return;
    }
    const requestedStart = params.get("t");
    const startSeconds = requestedStart && /^\d+$/.test(requestedStart)
      ? Number(requestedStart)
      : 0;
    const requestedEnd = params.get("end");
    const parsedEnd = requestedEnd && /^\d+$/.test(requestedEnd)
      ? Number(requestedEnd)
      : 0;
    const coverageRange = state.subtitleCoverage.get(video.youtubeId)?.ranges.find(
      (range) => range.startSeconds === startSeconds
    );
    const returnToHighlights = params.get("from") === "highlights";
    const endSeconds = returnToHighlights && Number.isSafeInteger(parsedEnd) && parsedEnd > startSeconds
      ? parsedEnd
      : returnToHighlights ? coverageRange?.endSeconds || 0 : 0;
    showPlayerView(video, startSeconds, returnToHighlights, endSeconds);
  }

  function showListView() {
    stopPolling();
    state.playerReady = false;
    state.currentChapters = [];
    elements.chapterList.replaceChildren();
    elements.chapterSection.hidden = true;
    if (document.fullscreenElement === elements.playerFrame) {
      document.exitFullscreen().catch(() => {});
    }
    if (state.player && typeof state.player.destroy === "function") {
      state.player.destroy();
      state.player = null;
    }
    resetSubtitleDisplay("Fan subtitles are off.");
    state.selectedVideo = null;
    state.initialStartSeconds = 0;
    state.initialEndSeconds = 0;
    state.nextSkip = 0;
    state.highlightEnded = false;
    state.returnToHighlights = false;
    elements.backLink.href = "./";
    elements.backLink.textContent = "← Back to livestreams";
    elements.highlightStart.hidden = true;
    elements.highlightStart.textContent = "";
    elements.subtitleToggle.className = "button button-primary";
    elements.playerView.hidden = true;
    elements.listView.hidden = false;
    document.title = "PLAVE Livestream Guide";
  }

  async function showPlayerView(video, startSeconds, returnToHighlights, endSeconds) {
    showListView();
    state.selectedVideo = video;
    state.initialStartSeconds = Number.isSafeInteger(startSeconds) && startSeconds >= 0 ? startSeconds : 0;
    state.initialEndSeconds = Number.isSafeInteger(endSeconds) && endSeconds > state.initialStartSeconds
      ? endSeconds
      : 0;
    state.highlightEnded = false;
    state.returnToHighlights = returnToHighlights;
    elements.listView.hidden = true;
    elements.playerView.hidden = false;
    elements.backLink.href = returnToHighlights ? "highlights.html" : video.creator ? guestDetailUrl(video.youtubeId) : "./";
    elements.backLink.textContent = returnToHighlights
      ? "← Back to highlights"
      : video.creator ? "← Back to video chapters" : "← Back to livestreams";
    elements.playerTitle.textContent = video.title;
    setStatus(elements.playerStatus, video.youtubeId);
    if (video.skips?.length) elements.playerStatus.textContent += " · Includes a playback skip";
    elements.youtubeLink.href = `https://www.youtube.com/watch?v=${encodeURIComponent(video.youtubeId)}`
      + (state.initialStartSeconds ? `&t=${state.initialStartSeconds}s` : "");
    elements.playerMessage.hidden = true;
    elements.highlightStart.hidden = state.initialStartSeconds === 0 && !video.creator;
    elements.highlightStart.textContent = state.initialStartSeconds > 0 || video.creator
      ? `Preparing subtitled ${video.creator ? "excerpt" : "scene"} ${formatHighlightRange()}…`
      : "";
    elements.subtitleToggle.className = state.initialStartSeconds > 0
      ? "button button-secondary"
      : "button button-primary";
    document.title = `${video.title} — PLAVE Lives`;

    const hasSubtitles = hasAnySubtitles(video.youtubeId);
    state.cues = [];
    state.subtitlesEnabled = false;
    elements.subtitleToggle.disabled = !hasSubtitles;
    elements.subtitleToggle.textContent = hasSubtitles ? "Turn fan subtitles on" : "Fan subtitles unavailable";
    elements.fullscreenToggle.hidden = !supportsPlayerFullscreen() || !hasSubtitles;
    elements.fullscreenToggle.disabled = true;
    updateFullscreenButton();
    renderChapters(video.youtubeId);

    if (hasSubtitles) await loadVtt(video.youtubeId);
    try {
      await loadYouTubeApi();
      if (state.selectedVideo === video) createPlayer(video.youtubeId, state.initialStartSeconds);
    } catch (error) {
      showMessage(elements.playerMessage, "The YouTube player could not be loaded. Check your connection or open the video on YouTube.", true);
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function handleBackLink(event) {
    event.preventDefault();
    if (state.returnToHighlights) {
      window.location.href = "highlights.html";
      return;
    }
    if (state.selectedVideo?.creator) {
      window.location.href = guestDetailUrl(state.selectedVideo.youtubeId);
      return;
    }
    if (history.state && history.state.fromList) history.back();
    else {
      history.replaceState({}, "", window.location.pathname);
      route();
    }
  }

  function loadYouTubeApi() {
    if (window.YT && window.YT.Player) return Promise.resolve();
    if (window.youtubeApiPromise) return window.youtubeApiPromise;
    window.youtubeApiPromise = new Promise((resolve, reject) => {
      const previousReady = window.onYouTubeIframeAPIReady;
      const timeout = window.setTimeout(() => reject(new Error("YouTube API timeout")), 12000);
      window.onYouTubeIframeAPIReady = function () {
        window.clearTimeout(timeout);
        if (typeof previousReady === "function") previousReady();
        resolve();
      };
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error("YouTube API failed"));
      };
      document.head.appendChild(script);
    });
    return window.youtubeApiPromise;
  }

  function createPlayer(videoId, startSeconds) {
    if (!document.getElementById("youtube-player")) {
      const mount = document.createElement("div");
      mount.id = "youtube-player";
      document.getElementById("player-frame").prepend(mount);
    }
    state.player = new window.YT.Player("youtube-player", {
      videoId,
      width: "100%",
      height: "100%",
      playerVars: {
        playsinline: 1,
        rel: 0,
        start: startSeconds || 0,
        cc_load_policy: 0,
        cc_lang_pref: "en"
      },
      events: {
        onReady: () => {
          state.playerReady = true;
          startPolling();
          elements.fullscreenToggle.disabled = !state.cues.length;
          setChapterButtonsDisabled(false);
          disableYouTubeCaptions();
          if (startSeconds > 0 || state.selectedVideo?.creator) {
            prepareHighlightedScene();
            const label = state.selectedVideo?.creator ? "excerpt" : "scene";
            elements.highlightStart.textContent = `Ready for subtitled ${label} ${formatHighlightRange()} — tap Play in the YouTube video`;
          }
        },
        onStateChange: handlePlayerStateChange,
        onApiChange: disableYouTubeCaptions,
        onAutoplayBlocked: () => {
          elements.highlightStart.hidden = state.initialStartSeconds <= 0 && !state.selectedVideo?.creator;
        },
        onError: () => {
          state.playerReady = false;
          elements.highlightStart.hidden = true;
          elements.fullscreenToggle.disabled = true;
          setChapterButtonsDisabled(true);
          showMessage(
            elements.playerMessage,
            "This video cannot be played in the embedded player. Use “Open on YouTube” instead.",
            true
          );
        }
      }
    });
  }

  function prepareHighlightedScene() {
    if (
      !state.playerReady
      || !state.player
      || (state.initialStartSeconds <= 0 && !state.selectedVideo?.creator)
      || typeof state.player.seekTo !== "function"
    ) return;
    state.player.seekTo(state.initialStartSeconds, true);
    if (state.cues.length && !state.subtitlesEnabled) toggleSubtitles();
    centerPlayerInView();
    window.setTimeout(centerPlayerInView, 250);
  }

  function disableYouTubeCaptions() {
    if (!state.player || typeof state.player.setOption !== "function") return;
    try {
      state.player.setOption("captions", "track", {});
    } catch (error) {
      // YouTube does not expose caption-track control in every player version.
    }
  }

  function handlePlayerStateChange(event) {
    if (
      (state.initialStartSeconds > 0 || state.selectedVideo?.creator)
      && window.YT
      && window.YT.PlayerState
      && event.data === window.YT.PlayerState.PLAYING
    ) {
      disableYouTubeCaptions();
      if (!state.highlightEnded) elements.highlightStart.hidden = true;
    }
  }

  async function loadVtt(videoId) {
    try {
      const coverage = getSubtitleCoverage(videoId);
      const directory = coverage === "guest" ? "guest-subtitles"
        : coverage === "highlights" ? "highlight-subtitles" : "subtitles";
      const response = await fetch(`${directory}/${encodeURIComponent(videoId)}.vtt`, { cache: "no-cache" });
      if (!response.ok) throw new Error("VTT missing");
      const cues = parseVtt(await response.text());
      if (cues.length === 0) throw new Error("VTT invalid");
      state.cues = cues;
      elements.subtitleToggle.disabled = false;
    } catch (error) {
      state.cues = [];
      elements.subtitleToggle.disabled = true;
      elements.subtitleToggle.textContent = "Fan subtitles unavailable";
      showMessage(
        elements.playerMessage,
        error.message === "VTT missing"
          ? "The fan subtitle file is listed but could not be found. The video can still be watched."
          : "The fan subtitle file is invalid or contains no readable cues. The video can still be watched.",
        true
      );
    }
  }

  function parseVtt(source) {
    const text = source.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
    const lines = text.split("\n");
    if (lines.length === 0 || !/^WEBVTT(?:\s|$)/.test(lines[0].trim())) return [];
    const cues = [];
    let index = 1;

    while (index < lines.length) {
      while (index < lines.length && !lines[index].trim()) index += 1;
      if (index >= lines.length) break;

      if (/^(NOTE|STYLE|REGION)(?:\s|$)/.test(lines[index].trim())) {
        while (index < lines.length && lines[index].trim()) index += 1;
        continue;
      }

      let timingLine = lines[index].trim();
      if (!timingLine.includes("-->")) {
        index += 1;
        if (index >= lines.length) break;
        timingLine = lines[index].trim();
      }

      const match = timingLine.match(/^(\S+)\s+-->\s+(\S+)(?:\s+.*)?$/);
      if (!match) {
        while (index < lines.length && lines[index].trim()) index += 1;
        continue;
      }
      const start = parseTimestamp(match[1]);
      const end = parseTimestamp(match[2]);
      index += 1;
      const cueLines = [];
      while (index < lines.length && lines[index].trim()) {
        cueLines.push(lines[index]);
        index += 1;
      }
      if (start !== null && end !== null && end > start && cueLines.length) {
        cues.push({ start, end, text: cueLines.join("\n") });
      }
    }
    return cues.sort((a, b) => a.start - b.start);
  }

  function parseTimestamp(value) {
    const parts = value.replace(",", ".").split(":");
    if (parts.length !== 2 && parts.length !== 3) return null;
    const secondsPart = Number(parts.pop());
    const minutes = Number(parts.pop());
    const hours = parts.length ? Number(parts.pop()) : 0;
    if (![secondsPart, minutes, hours].every(Number.isFinite)) return null;
    if (secondsPart < 0 || secondsPart >= 60 || minutes < 0 || minutes >= 60 || hours < 0) return null;
    return hours * 3600 + minutes * 60 + secondsPart;
  }

  function renderChapters(videoId) {
    const chapters = state.chaptersByVideo.get(videoId) || [];
    state.currentChapters = chapters;
    elements.chapterList.replaceChildren();
    elements.chapterSection.hidden = chapters.length === 0;
    if (!chapters.length) return;

    const fragment = document.createDocumentFragment();
    chapters.forEach((chapter, index) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chapter-button";
      button.disabled = !state.playerReady;

      const time = document.createElement("span");
      time.className = "chapter-time";
      time.textContent = formatChapterTime(chapter.startSeconds);

      const title = document.createElement("span");
      title.className = "chapter-title";
      const titleText = document.createElement("span");
      titleText.className = "chapter-title-text";
      titleText.textContent = chapter.title;
      title.appendChild(titleText);

      const nextStart = chapters[index + 1]?.startSeconds ?? Number.POSITIVE_INFINITY;
      if (isHotChapter(videoId, chapter.startSeconds, nextStart)) {
        const badge = document.createElement("span");
        badge.className = "chapter-hot-badge";
        badge.textContent = "🔥 Most replayed";
        title.appendChild(badge);
      }

      button.append(time, title);
      button.addEventListener("click", () => seekToChapter(chapter.startSeconds));
      item.appendChild(button);
      fragment.appendChild(item);
    });
    elements.chapterList.appendChild(fragment);
  }

  function isHotChapter(videoId, chapterStart, chapterEnd) {
    const points = state.heatmapsByVideo.get(videoId) || [];
    return points.some((point) => {
      const midpoint = point.startSeconds + (point.endSeconds - point.startSeconds) / 2;
      return midpoint >= chapterStart && midpoint < chapterEnd && point.value >= HOT_CHAPTER_THRESHOLD;
    });
  }

  function formatChapterTime(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function formatHighlightRange() {
    const start = formatChapterTime(state.initialStartSeconds);
    return state.initialEndSeconds > state.initialStartSeconds
      ? `${start}–${formatChapterTime(state.initialEndSeconds)}`
      : `at ${start}`;
  }

  function setChapterButtonsDisabled(disabled) {
    elements.chapterList.querySelectorAll("button").forEach((button) => {
      button.disabled = disabled;
    });
  }

  function seekToChapter(startSeconds) {
    if (!state.playerReady || !state.player || typeof state.player.seekTo !== "function") return;
    centerPlayerInView();
    window.setTimeout(centerPlayerInView, 250);
    window.setTimeout(ensurePlayerInView, 450);
    state.player.seekTo(startSeconds, true);
    if (state.cues.length && !state.subtitlesEnabled) toggleSubtitles();
    if (typeof state.player.playVideo === "function") state.player.playVideo();
  }

  function centerPlayerInView() {
    const rect = elements.playerFrame.getBoundingClientRect();
    const viewportHeight = window.visualViewport
      ? window.visualViewport.height
      : window.innerHeight;
    const targetTop = window.scrollY + rect.top - Math.max(0, (viewportHeight - rect.height) / 2);
    window.scrollTo(0, Math.max(0, targetTop));
  }

  function ensurePlayerInView() {
    const rect = elements.playerFrame.getBoundingClientRect();
    const viewportHeight = window.visualViewport
      ? window.visualViewport.height
      : window.innerHeight;
    const desiredTop = Math.max(0, (viewportHeight - rect.height) / 2);
    if (Math.abs(rect.top - desiredTop) <= 24) return;

    // Safari can ignore scripted scrolling while the YouTube iframe takes
    // focus. A same-page fragment navigation uses Safari's native scrolling.
    const baseUrl = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState(window.history.state, "", baseUrl);
    window.location.replace(`${baseUrl}#player-frame`);
  }

  function toggleSubtitles() {
    if (!state.cues.length) return;
    state.subtitlesEnabled = !state.subtitlesEnabled;
    elements.subtitleToggle.textContent = state.subtitlesEnabled
      ? "Turn fan subtitles off"
      : "Turn fan subtitles on";
    elements.subtitleToggle.setAttribute("aria-pressed", String(state.subtitlesEnabled));
    state.activeCueKey = null;
    if (!state.subtitlesEnabled) resetSubtitleDisplay("Fan subtitles are off.");
    else updateSubtitles();
  }

  function supportsPlayerFullscreen() {
    return Boolean(
      elements.playerFrame
      && typeof elements.playerFrame.requestFullscreen === "function"
      && typeof document.exitFullscreen === "function"
    );
  }

  async function togglePlayerFullscreen() {
    if (!supportsPlayerFullscreen() || !state.cues.length) return;
    try {
      if (document.fullscreenElement === elements.playerFrame) {
        await document.exitFullscreen();
        return;
      }
      if (!state.subtitlesEnabled) toggleSubtitles();
      await elements.playerFrame.requestFullscreen();
    } catch (error) {
      showMessage(
        elements.playerMessage,
        "Fullscreen could not be opened. The video and fan subtitles still work in the normal view.",
        true
      );
    }
  }

  function updateFullscreenButton() {
    const isFullscreen = document.fullscreenElement === elements.playerFrame;
    elements.fullscreenToggle.textContent = isFullscreen
      ? "Exit fullscreen"
      : "Fullscreen with fan subtitles";
    elements.fullscreenToggle.setAttribute("aria-pressed", String(isFullscreen));
  }

  function startPolling() {
    stopPolling();
    updateSubtitles();
    state.pollTimer = window.setInterval(updateSubtitles, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (state.pollTimer !== null) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function updateSubtitles() {
    if (!state.player || typeof state.player.getCurrentTime !== "function") return;
    const currentTime = state.player.getCurrentTime();
    const skip = state.selectedVideo?.skips?.find((range) => range.from <= currentTime && currentTime < range.to);
    const playing = window.YT?.PlayerState?.PLAYING;
    if (skip && playing !== undefined && typeof state.player.seekTo === "function" && state.player.getPlayerState?.() === playing) {
      if (state.nextSkip !== skip.to) {
        state.nextSkip = skip.to;
        state.player.seekTo(skip.to, true);
      }
      return;
    }
    state.nextSkip = 0;
    if (!state.subtitlesEnabled) return;
    if (state.initialEndSeconds > state.initialStartSeconds && currentTime >= state.initialEndSeconds) {
      if (!state.highlightEnded) {
        state.highlightEnded = true;
        if (typeof state.player.pauseVideo === "function") state.player.pauseVideo();
      }
      const endedKey = `highlight-ended:${state.initialEndSeconds}`;
      if (state.activeCueKey !== endedKey) {
        state.activeCueKey = endedKey;
        elements.subtitleOverlay.textContent = "";
        elements.subtitleOverlay.classList.remove("has-text");
        elements.subtitleFallback.textContent = state.selectedVideo?.creator
          ? "End of this subtitled excerpt. Press Play again to continue without fan subtitles."
          : "End of this subtitled highlight. Choose another highlight, or press Play again to continue without fan subtitles.";
      }
      elements.highlightStart.textContent = state.selectedVideo?.creator
        ? "End of this subtitled excerpt — press Play again to continue."
        : "End of this subtitled highlight — choose another scene or press Play again to continue.";
      elements.highlightStart.hidden = false;
      return;
    }
    if (state.highlightEnded) {
      state.highlightEnded = false;
      elements.highlightStart.hidden = true;
      state.activeCueKey = null;
    }
    const active = state.cues.filter((cue) => currentTime >= cue.start && currentTime < cue.end);
    const key = active.map((cue) => `${cue.start}:${cue.end}:${cue.text}`).join("|");
    if (key === state.activeCueKey) return;
    state.activeCueKey = key;
    const text = active.map((cue) => cue.text).join("\n");
    elements.subtitleOverlay.textContent = text;
    elements.subtitleFallback.textContent = text || "…";
    elements.subtitleOverlay.classList.toggle("has-text", Boolean(text));
  }

  function resetSubtitleDisplay(message) {
    state.subtitlesEnabled = false;
    state.activeCueKey = null;
    elements.subtitleOverlay.textContent = "";
    elements.subtitleOverlay.classList.remove("has-text");
    elements.subtitleFallback.textContent = message;
    elements.subtitleToggle.setAttribute("aria-pressed", "false");
  }

  function showMessage(element, message, isError) {
    element.textContent = message;
    element.className = isError ? "message message-error" : "message";
    element.hidden = false;
  }
})();
