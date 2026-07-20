(function () {
  "use strict";

  const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{6,20}$/;
  const POLL_INTERVAL_MS = 150;
  const state = {
    videos: [],
    subtitleIds: new Set(),
    subtitleManifestLoaded: false,
    selectedVideo: null,
    player: null,
    cues: [],
    subtitlesEnabled: false,
    activeCueKey: null,
    pollTimer: null
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
    subtitleToggle: document.getElementById("subtitle-toggle"),
    fullscreenToggle: document.getElementById("fullscreen-toggle"),
    playerFrame: document.getElementById("player-frame"),
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

    const [videosResult, subtitlesResult] = await Promise.allSettled([
      fetchJson("data/videos.json"),
      fetchJson("data/subtitles.json")
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

  function renderVideoList() {
    elements.videoGrid.replaceChildren();
    const onlySubtitled = elements.filter.value === "subtitled";
    const videos = onlySubtitled
      ? state.videos.filter((video) => state.subtitleIds.has(video.youtubeId))
      : state.videos;

    if (!state.subtitleManifestLoaded) {
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
    if (!state.subtitleManifestLoaded) {
      element.textContent = "Fan subtitle status unknown";
      element.classList.add("status-unknown");
    } else if (state.subtitleIds.has(videoId)) {
      element.textContent = "English fan subtitles available";
      element.classList.add("status-available");
    } else {
      element.textContent = "No fan subtitles yet";
      element.classList.add("status-missing");
    }
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
    showPlayerView(video);
  }

  function showListView() {
    stopPolling();
    if (document.fullscreenElement === elements.playerFrame) {
      document.exitFullscreen().catch(() => {});
    }
    if (state.player && typeof state.player.destroy === "function") {
      state.player.destroy();
      state.player = null;
    }
    resetSubtitleDisplay("Fan subtitles are off.");
    state.selectedVideo = null;
    elements.playerView.hidden = true;
    elements.listView.hidden = false;
    document.title = "PLAVE Lives with English Fan Subtitles";
  }

  async function showPlayerView(video) {
    showListView();
    state.selectedVideo = video;
    elements.listView.hidden = true;
    elements.playerView.hidden = false;
    elements.playerTitle.textContent = video.title;
    setStatus(elements.playerStatus, video.youtubeId);
    elements.youtubeLink.href = `https://www.youtube.com/watch?v=${encodeURIComponent(video.youtubeId)}`;
    elements.playerMessage.hidden = true;
    document.title = `${video.title} — PLAVE Lives`;

    const hasSubtitles = state.subtitleManifestLoaded && state.subtitleIds.has(video.youtubeId);
    state.cues = [];
    state.subtitlesEnabled = false;
    elements.subtitleToggle.disabled = !hasSubtitles;
    elements.subtitleToggle.textContent = hasSubtitles ? "Turn fan subtitles on" : "Fan subtitles unavailable";
    elements.fullscreenToggle.hidden = !supportsPlayerFullscreen() || !hasSubtitles;
    elements.fullscreenToggle.disabled = true;
    updateFullscreenButton();

    if (hasSubtitles) await loadVtt(video.youtubeId);
    try {
      await loadYouTubeApi();
      if (state.selectedVideo === video) createPlayer(video.youtubeId);
    } catch (error) {
      showMessage(elements.playerMessage, "The YouTube player could not be loaded. Check your connection or open the video on YouTube.", true);
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function handleBackLink(event) {
    event.preventDefault();
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

  function createPlayer(videoId) {
    if (!document.getElementById("youtube-player")) {
      const mount = document.createElement("div");
      mount.id = "youtube-player";
      document.getElementById("player-frame").prepend(mount);
    }
    state.player = new window.YT.Player("youtube-player", {
      videoId,
      width: "100%",
      height: "100%",
      playerVars: { playsinline: 1, rel: 0 },
      events: {
        onReady: () => {
          startPolling();
          elements.fullscreenToggle.disabled = !state.cues.length;
        },
        onError: () => showMessage(
          elements.playerMessage,
          "This video cannot be played in the embedded player. Use “Open on YouTube” instead.",
          true
        )
      }
    });
  }

  async function loadVtt(videoId) {
    try {
      const response = await fetch(`subtitles/${encodeURIComponent(videoId)}.vtt`, { cache: "no-cache" });
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
