(function () {
  "use strict";

  const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{6,20}$/;
  const POLL_INTERVAL_MS = 150;
  const HOT_CHAPTER_THRESHOLD = 0.5;
  const state = {
    videos: [],
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
    elements.filter.addEventListener("change", renderVideoList);
    elements.subtitleToggle.addEventListener("click", toggleSubtitles);
    elements.fullscreenToggle.addEventListener("click", togglePlayerFullscreen);
    elements.backLink.addEventListener("click", handleBackLink);
    document.addEventListener("fullscreenchange", updateFullscreenButton);
    window.addEventListener("popstate", route);

    const [videosResult, subtitlesResult, coverageResult, chaptersResult, heatmapsResult] = await Promise.allSettled([
      fetchJson("data/videos.json"),
      fetchJson("data/subtitles.json"),
      fetchJson("data/subtitle-coverage.json"),
      fetchJson("data/chapters.json"),
      fetchJson("data/heatmaps.json")
    ]);

    if (videosResult.status === "fulfilled" && Array.isArray(videosResult.value)) {
      state.videos = videosResult.value.filter(isValidVideo);
    } else {
      showMessage(elements.listMessage, "The livestream list could not be loaded. Please try again later.", true);
      return;
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

    if (!state.subtitleManifestLoaded && !state.coverageManifestLoaded) {
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

    if (video.publishedAt) {
      const date = document.createElement("p");
      date.className = "video-date";
      date.textContent = formatDate(video.publishedAt);
      content.appendChild(date);
    }

    content.appendChild(createStatus(video.youtubeId));

    const watch = document.createElement("a");
    watch.className = "button button-primary";
    watch.href = `?v=${encodeURIComponent(video.youtubeId)}`;
    watch.textContent = "Watch";
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
    if (!state.subtitleManifestLoaded && !state.coverageManifestLoaded) {
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
    const video = state.videos.find((item) => item.youtubeId === requestedId);
    if (!video) {
      showListView();
      showMessage(elements.listMessage, "This video is not in the official PLAVE Live list. Choose a livestream below.", true);
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
    const endSeconds = Number.isSafeInteger(parsedEnd) && parsedEnd > startSeconds
      ? parsedEnd
      : coverageRange?.endSeconds || 0;
    showPlayerView(video, startSeconds, params.get("from") === "highlights", endSeconds);
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
    state.highlightEnded = false;
    state.returnToHighlights = false;
    elements.backLink.href = "./";
    elements.backLink.textContent = "← Back to livestreams";
    elements.highlightStart.hidden = true;
    elements.highlightStart.textContent = "";
    elements.subtitleToggle.className = "button button-primary";
    elements.playerView.hidden = true;
    elements.listView.hidden = false;
    document.title = "PLAVE Lives with English Fan Subtitles";
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
    elements.backLink.href = returnToHighlights ? "highlights.html" : "./";
    elements.backLink.textContent = returnToHighlights
      ? "← Back to Most replayed scenes"
      : "← Back to livestreams";
    elements.playerTitle.textContent = video.title;
    setStatus(elements.playerStatus, video.youtubeId);
    elements.youtubeLink.href = `https://www.youtube.com/watch?v=${encodeURIComponent(video.youtubeId)}`
      + (state.initialStartSeconds ? `&t=${state.initialStartSeconds}s` : "");
    elements.playerMessage.hidden = true;
    elements.highlightStart.hidden = state.initialStartSeconds === 0;
    elements.highlightStart.textContent = state.initialStartSeconds > 0
      ? `Preparing subtitled scene ${formatHighlightRange()}…`
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
          if (startSeconds > 0) {
            prepareHighlightedScene();
            elements.highlightStart.textContent = `Ready for subtitled scene ${formatHighlightRange()} — tap Play in the YouTube video`;
          }
        },
        onStateChange: handlePlayerStateChange,
        onApiChange: disableYouTubeCaptions,
        onAutoplayBlocked: () => {
          elements.highlightStart.hidden = state.initialStartSeconds <= 0;
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
      || state.initialStartSeconds <= 0
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
      state.initialStartSeconds > 0
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
      const directory = coverage === "highlights" ? "highlight-subtitles" : "subtitles";
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
    if (!state.subtitlesEnabled || !state.player || typeof state.player.getCurrentTime !== "function") return;
    const currentTime = state.player.getCurrentTime();
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
        elements.subtitleFallback.textContent = "End of this subtitled highlight. Choose another Most replayed scene, or press Play again to continue without fan subtitles.";
      }
      elements.highlightStart.textContent = "End of this subtitled highlight — choose another scene or press Play again to continue.";
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
