(function () {
  "use strict";

  const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{6,20}$/;
  const LAST_RANDOM_SCENE_KEY = "pfs-last-random-highlight";
  let randomScenes = [];
  const elements = {
    message: document.getElementById("highlights-message"),
    groups: document.getElementById("highlight-groups"),
    randomButton: document.getElementById("random-highlight")
  };

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    elements.randomButton.addEventListener("click", openRandomHighlight);
    try {
      const response = await fetch("data/highlights.json", { cache: "no-cache" });
      if (!response.ok) throw new Error("Highlights request failed");
      const highlights = normalizeHighlights(await response.json());
      renderHighlights(highlights);
    } catch (error) {
      showMessage(
        "The Most replayed scenes could not be loaded. Please try again later.",
        true
      );
    }
  }

  function normalizeHighlights(value) {
    if (!Array.isArray(value)) throw new Error("Invalid highlights data");
    return value.map((stream) => {
      if (
        !stream
        || typeof stream !== "object"
        || typeof stream.youtubeId !== "string"
        || !VIDEO_ID_PATTERN.test(stream.youtubeId)
        || typeof stream.displayTitle !== "string"
        || !stream.displayTitle.trim()
        || (stream.coverage !== "full" && stream.coverage !== "highlights")
        || !Array.isArray(stream.scenes)
      ) throw new Error("Invalid highlight stream");

      let previousStart = -1;
      const scenes = stream.scenes.map((scene) => {
        const startSeconds = scene?.startSeconds;
        const endSeconds = scene?.endSeconds;
        const title = typeof scene?.title === "string" ? scene.title.trim() : "";
        if (
          !Number.isInteger(startSeconds)
          || !Number.isInteger(endSeconds)
          || startSeconds < 0
          || endSeconds <= startSeconds
          || startSeconds <= previousStart
          || !title
          || title.length > 120
        ) throw new Error("Invalid highlight scene");
        previousStart = startSeconds;
        return { startSeconds, endSeconds, title };
      });
      if (!scenes.length) throw new Error("Empty highlight stream");
      return {
        youtubeId: stream.youtubeId,
        date: typeof stream.date === "string" ? stream.date : "",
        displayTitle: stream.displayTitle.trim(),
        coverage: stream.coverage,
        scenes
      };
    });
  }

  function renderHighlights(highlights) {
    elements.groups.replaceChildren();
    randomScenes = highlights.flatMap((stream) => stream.scenes.map((scene) => ({
      youtubeId: stream.youtubeId,
      startSeconds: scene.startSeconds,
      endSeconds: scene.endSeconds,
      coverage: stream.coverage,
      title: scene.title
    })));
    elements.randomButton.disabled = randomScenes.length === 0;
    if (!highlights.length) {
      showMessage(
        "No subtitled Most replayed scenes are available yet. New highlights will appear here as they are prepared.",
        false
      );
      return;
    }
    elements.message.hidden = true;
    const fragment = document.createDocumentFragment();
    highlights.forEach((stream) => fragment.appendChild(createStreamGroup(stream)));
    elements.groups.appendChild(fragment);
  }

  function openRandomHighlight() {
    if (!randomScenes.length) return;

    const previousKey = readLastRandomScene();
    const choices = randomScenes.length > 1
      ? randomScenes.filter((scene) => sceneKey(scene) !== previousKey)
      : randomScenes;
    const selected = choices[Math.floor(Math.random() * choices.length)];
    const selectedKey = sceneKey(selected);

    try {
      window.sessionStorage.setItem(LAST_RANDOM_SCENE_KEY, selectedKey);
    } catch (error) {
      // Random navigation still works when Safari blocks session storage.
    }

    elements.randomButton.disabled = true;
    elements.randomButton.textContent = "Opening random scene…";
    window.location.assign(sceneUrl(
      selected.youtubeId,
      selected.startSeconds,
      selected.endSeconds,
      selected.coverage
    ));
  }

  function readLastRandomScene() {
    try {
      return window.sessionStorage.getItem(LAST_RANDOM_SCENE_KEY) || "";
    } catch (error) {
      return "";
    }
  }

  function sceneKey(scene) {
    return `${scene.youtubeId}:${scene.startSeconds}`;
  }

  function sceneUrl(youtubeId, startSeconds, endSeconds, coverage) {
    const endParameter = coverage === "highlights" ? `&end=${endSeconds}` : "";
    return `./?v=${encodeURIComponent(youtubeId)}&t=${startSeconds}${endParameter}&from=highlights`;
  }

  function createStreamGroup(stream) {
    const section = document.createElement("section");
    section.className = "highlight-group";

    const header = document.createElement("div");
    header.className = "highlight-group-header";

    const date = document.createElement("p");
    date.className = "highlight-date";
    date.textContent = /^\d{4}-\d{2}-\d{2}$/.test(stream.date) ? stream.date : "Date unavailable";

    const title = document.createElement("h2");
    title.className = "highlight-stream-title";
    title.textContent = stream.displayTitle;

    const status = document.createElement("p");
    status.className = "subtitle-status";
    status.textContent = stream.coverage === "full"
      ? "Complete English fan subtitles available"
      : "English subtitles available for highlighted scenes";
    status.classList.add(stream.coverage === "full" ? "status-available" : "status-highlight");

    header.append(date, title, status);

    const list = document.createElement("ol");
    list.className = "highlight-scene-list";
    stream.scenes.forEach((scene) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.className = "highlight-scene-link";
      link.href = sceneUrl(
        stream.youtubeId,
        scene.startSeconds,
        scene.endSeconds,
        stream.coverage
      );

      const time = document.createElement("span");
      time.className = "highlight-scene-time";
      time.textContent = formatTime(scene.startSeconds);

      const sceneTitle = document.createElement("span");
      sceneTitle.className = "highlight-scene-title";
      sceneTitle.textContent = scene.title;

      const badge = document.createElement("span");
      badge.className = "chapter-hot-badge";
      badge.textContent = "🔥 Most replayed";

      link.append(time, sceneTitle, badge);
      item.appendChild(link);
      list.appendChild(item);
    });

    section.append(header, list);
    return section;
  }

  function formatTime(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return hours > 0
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
      : `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function showMessage(text, isError) {
    elements.message.textContent = text;
    elements.message.className = isError ? "message message-error" : "message";
    elements.message.hidden = false;
  }
})();
