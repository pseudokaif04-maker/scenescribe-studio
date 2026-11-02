(() => {
  "use strict";

  /* ── Constants ─────────────────────────────────────────── */

  const FALLBACK_TONES = [
    { value: "auto", label: "Auto (from the edit)" },
    { value: "cinematic", label: "Cinematic" },
    { value: "playful", label: "Playful" },
    { value: "bold", label: "Bold" },
    { value: "warm", label: "Warm" },
    { value: "minimal", label: "Minimal" },
    { value: "professional", label: "Professional" }
  ];

  const FALLBACK_PLATFORMS = [
    { value: "instagram", label: "Instagram", limit: 2200 },
    { value: "tiktok", label: "TikTok", limit: 2200 },
    { value: "youtube", label: "YouTube Shorts", limit: 5000 },
    { value: "linkedin", label: "LinkedIn", limit: 3000 },
    { value: "x", label: "X", limit: 280 }
  ];

  const ALLOWED_EXTENSIONS = new Set(["mp4", "mov", "m4v", "webm", "mkv", "avi"]);
  const MIME_EXTENSIONS = new Set([
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo"
  ]);
  const JOB_ID_RE = /^[a-f0-9]{32}$/;
  const CLIP_RUN_ID_RE = /^[a-f0-9]{32}$/;
  const STAGE_ORDER = ["upload", "probe", "frames", "onscreen", "audio", "speech", "read", "write"];
  const FORGE_STAGE_ORDER = ["source", "moments", "render", "package"];
  const FORGE_STAGE_STATES = {
    source: "Opening",
    moments: "Finding",
    render: "Cutting",
    package: "Packaging",
    queued: "Queued",
    done: "Done"
  };
  const STAGE_STATES = {
    upload: "Sending",
    probe: "Opening",
    frames: "Reading",
    onscreen: "Scanning",
    audio: "Listening",
    speech: "Transcribing",
    read: "Building",
    write: "Writing"
  };
  const MAX_SEGMENTS = 8;
  const HOME_TITLE = "SceneScribe Studio - every frame has something to say";
  const FORGE_TITLE = "ClipForge — from link to clip deck";
  const FILM_ICON = '<svg viewBox="0 0 32 32" aria-hidden="true"><rect x="5" y="8" width="22" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="m14 13 6 3-6 3v-6Z" fill="currentColor"/></svg>';

  const state = {
    health: null,
    toneOptions: [],
    platformOptions: [],
    mode: "landing",
    file: null,
    inspection: null,
    jobId: null,
    job: null,
    result: null,
    captionSet: null,
    captions: [],
    selectedId: null,
    editingId: null,
    tone: "auto",
    platform: "instagram",
    seed: 0,
    uploadXhr: null,
    pollTimer: null,
    pollFailures: 0,
    elapsedTimer: null,
    processStarted: 0,
    currentStageIndex: 0,
    toastTimer: null,
    remixToken: 0,
    errorRetryHandler: null,
    frames: [],
    activeFrame: -1,
    clipRunId: null,
    clipRun: null,
    clipPollTimer: null,
    clipPollFailures: 0,
    clipElapsedTimer: null,
    clipRunStarted: 0,
    forgeSubmitting: false,
    forgePayload: null,
    forgeCaptionBusy: false,
    forgeRetryHandler: null,
    lastForgeStage: "source"
  };

  const dom = {};

  /* ── Boot ───────────────────────────────────────────────── */

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }

  function start() {
    init().catch((error) => {
      console.error("SceneScribe failed to start", error);
      showToast("The studio had trouble starting. Reload the page to try again.");
    });
  }

  async function init() {
    cacheDom();
    bindEvents();

    const initialJob = jobIdFromUrl();
    const initialClipRun = clipRunIdFromUrl();
    const initialForge = forgeRequestedFromUrl();
    if (initialJob) {
      if (initialClipRun && CLIP_RUN_ID_RE.test(initialClipRun)) {
        state.clipRunId = initialClipRun;
      }
      prepareLoadingProcess();
    }

    await loadHealth();
    populateControls();

    if (initialJob) {
      if (!JOB_ID_RE.test(initialJob)) {
        history.replaceState({}, "", "/");
        setView("landing", { focus: false });
        showToast("That result link doesn’t look right.");
        return;
      }
      await openJob(initialJob, { fromLink: true });
      return;
    }

    if (initialClipRun) {
      await openClipRun(initialClipRun, { fromLink: true });
      return;
    }

    if (initialForge) {
      openForgeLanding({ push: false, focus: false });
      return;
    }

    setView("landing", { focus: false });
  }

  function cacheDom() {
    [
      "landingView", "processView", "forgeView", "studioView", "siteHeader", "siteFooter",
      "homeLink", "headerNew", "localPill", "localPillText", "appVersion",
      "dropzone", "fileInput", "dropIdle", "filePreview", "fileThumb", "fileName",
      "fileMeta", "clearFile", "uploadError", "readButton", "readButtonLabel",
      "dropHint", "uploadTitle", "upload", "capFfmpeg", "capSpeech", "capOcr",
      "capClipforge", "processTitle", "processMessage", "processPercent",
      "processElapsed", "progressBar", "progressFill", "stageList", "processStartOver",
      "processThumb", "processFileName", "processFileMeta", "processError",
      "processErrorText", "errorReset", "errorRetry",
      "forgeHomeLink", "forgeTitle", "forgeEngineStatus", "forgeEngineReason",
      "forgeWorkspace", "forgeForm", "forgeSource", "forgeCount", "forgeLength",
      "forgeAspect", "forgeReframe", "forgeCaptions", "forgeHook", "forgeMode",
      "forgeError", "forgeSubmit", "forgeSubmitLabel", "forgeCancel",
      "forgeProgress", "forgeProgressMessage", "forgePercent", "forgeElapsed",
      "forgeProgressBar", "forgeProgressFill", "forgeStageList", "forgeLog",
      "forgeRunError", "forgeRunErrorTitle", "forgeRunErrorText", "forgeRetry",
      "forgeBackToForm",
      "forgeResults", "forgeResultsTitle", "forgeResultsMeta", "clipDeckGrid",
      "forgeAgain", "forgeOpenFolder",
      "studioTitle", "studioMeta", "studioDeckLink", "shareButton", "downloadVideo",
      "videoPlayer", "videoPace", "frameCount", "frameRail", "paletteList",
      "specs", "moodBadge", "readSummary", "signalGrid", "quoteBlock",
      "quoteText", "quoteSource", "keywordRow", "onscreenDetails",
      "onscreenCount", "onscreenList", "transcriptQuality", "transcriptList",
      "warningNote", "warningText", "toneNote", "toneSelect", "platformSelect",
      "remixButton", "selectionLabel", "selectionCount", "copySelected",
      "exportCaptions", "captionGrid", "generatedLabel", "toast", "toastText"
    ].forEach((id) => {
      dom[id] = document.getElementById(id);
    });

    dom.views = [...document.querySelectorAll("[data-view]")];
    dom.newVideoLinks = [...document.querySelectorAll("[data-new-video]")];
    dom.forgeOpeners = [...document.querySelectorAll("[data-open-forge]")];
    dom.stageItems = [...dom.stageList.querySelectorAll("li")];
    dom.forgeStageItems = [...dom.forgeStageList.querySelectorAll("li")];
    dom.processMain = dom.processView.querySelector(".process-main");
    dom.videoFrame = document.getElementById("videoFrame");
  }

  /* ── Health & controls ──────────────────────────────────── */

  async function loadHealth() {
    try {
      const response = await fetch("/api/health", {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`Health check returned ${response.status}`);
      const health = await response.json();
      state.health = health;

      const engineReady = Boolean(health.ffmpeg && health.ffprobe);
      dom.localPill.classList.toggle("is-degraded", !engineReady);
      dom.localPillText.textContent = engineReady ? "On this device" : "Needs ffmpeg";
      setCapability(dom.capFfmpeg, "Video engine", engineReady);
      setCapability(dom.capSpeech, "Speech", Boolean(health.speech));
      setCapability(dom.capOcr, "On-screen text", Boolean(health.ocr));
      applyClipForgeHealth(health.clipforge);

      if (health.version) dom.appVersion.textContent = `v${health.version}`;
      const limit = Number(health.max_upload_mb) || 500;
      dom.dropHint.textContent = `MP4, MOV, WEBM, MKV — up to ${limit} MB. Landscape, vertical, short or long; SceneScribe adapts to the cut.`;
    } catch (error) {
      console.warn("Could not read local capabilities", error);
      state.health = null;
      dom.localPill.classList.add("is-degraded");
      dom.localPillText.textContent = "Local status unknown";
      setCapability(dom.capFfmpeg, "Video engine", null);
      setCapability(dom.capSpeech, "Speech", null);
      setCapability(dom.capOcr, "On-screen text", null);
      applyClipForgeHealth(null);
    }
  }

  function applyClipForgeHealth(clipforge) {
    const ready = clipforge?.available === true;
    setCapability(dom.capClipforge, "ClipForge", clipforge ? ready : null);
    if (!dom.forgeEngineStatus) return;
    dom.forgeEngineStatus.classList.toggle("is-ready", ready);
    dom.forgeEngineStatus.classList.toggle("is-off", Boolean(clipforge) && !ready);
    dom.forgeEngineStatus.textContent = ready
      ? "Ready"
      : clipforge
        ? "Unavailable"
        : "Unknown";
    if (dom.forgeEngineReason) {
      dom.forgeEngineReason.textContent = ready
        ? "ClipForge is installed and ready in its own local environment."
        : clipforge?.reason
          || "The local health check could not confirm ClipForge.";
    }
    updateForgeSubmitState();
  }

  function setCapability(node, label, available) {
    if (!node) return;
    node.classList.toggle("is-off", available === false);
    const dot = document.createElement("i");
    dot.setAttribute("aria-hidden", "true");
    node.replaceChildren(dot, document.createTextNode(available === false ? ` ${label} off` : ` ${label}`));
    node.title = available === false
      ? `${label} is not available on this machine.`
      : available === true
        ? `${label} is ready locally.`
        : `${label} status is unknown.`;
  }

  function populateControls() {
    const tones = Array.isArray(state.health?.tones) && state.health.tones.length
      ? state.health.tones
      : FALLBACK_TONES;
    const platforms = Array.isArray(state.health?.platforms) && state.health.platforms.length
      ? state.health.platforms
      : FALLBACK_PLATFORMS;

    state.toneOptions = tones.map((tone) => ({
      value: String(tone.value),
      label: String(tone.label),
      description: tone.description ? String(tone.description) : ""
    }));
    state.platformOptions = platforms.map((platform) => ({
      value: String(platform.value),
      label: String(platform.label),
      limit: Number(platform.limit) || 2200
    }));

    if (!state.toneOptions.some((tone) => tone.value === "auto")) {
      state.toneOptions.unshift(FALLBACK_TONES[0]);
    }

    dom.toneSelect.replaceChildren(...state.toneOptions.map((tone) => {
      const option = new Option(tone.label, tone.value);
      if (tone.description) option.title = tone.description;
      return option;
    }));

    dom.platformSelect.replaceChildren(...state.platformOptions.map((platform) => {
      return new Option(platform.label, platform.value);
    }));

    dom.toneSelect.value = state.tone;
    dom.platformSelect.value = state.platform;
  }

  /* ── Routing & views ────────────────────────────────────── */

  function jobIdFromUrl() {
    const value = new URLSearchParams(window.location.search).get("job");
    return value ? value.trim() : null;
  }

  function clipRunIdFromUrl() {
    const value = new URLSearchParams(window.location.search).get("clips");
    return value ? value.trim() : null;
  }

  function forgeRequestedFromUrl() {
    return new URLSearchParams(window.location.search).get("forge") === "1";
  }

  function setView(name, { focus = true } = {}) {
    state.mode = name;
    document.body.dataset.mode = name;
    dom.views.forEach((view) => {
      view.hidden = view.dataset.view !== name;
    });
    dom.headerNew.hidden = name === "landing";
    window.scrollTo({ top: 0, behavior: "auto" });

    if (name === "landing") {
      document.title = HOME_TITLE;
    } else if (name === "forge" && !state.clipRunId) {
      document.title = FORGE_TITLE;
    }

    if (focus) {
      const heading = name === "process"
        ? dom.processTitle
        : name === "studio"
          ? dom.studioTitle
          : name === "forge"
            ? dom.forgeTitle
            : null;
      if (heading) {
        requestAnimationFrame(() => heading.focus({ preventScroll: true }));
      }
    }
  }

  function updateUrlForJob(jobId, { push = false } = {}) {
    const params = new URLSearchParams();
    params.set("job", jobId);
    if (state.clipRunId && CLIP_RUN_ID_RE.test(state.clipRunId)) {
      params.set("clips", state.clipRunId);
    }
    const target = `/?${params.toString()}`;
    if (window.location.pathname + window.location.search === target) return;
    const method = push ? "pushState" : "replaceState";
    history[method]({ job: jobId, clips: state.clipRunId }, "", target);
  }

  function updateUrlForClipRun(runId, { push = false } = {}) {
    const target = `/?clips=${encodeURIComponent(runId)}`;
    if (window.location.pathname + window.location.search === target) return;
    const method = push ? "pushState" : "replaceState";
    history[method]({ clips: runId }, "", target);
  }

  function updateUrlForForge({ push = false } = {}) {
    const target = "/?forge=1";
    if (window.location.pathname + window.location.search === target) return;
    const method = push ? "pushState" : "replaceState";
    history[method]({ forge: true }, "", target);
  }

  function clearJobUrl({ push = true } = {}) {
    if (window.location.pathname === "/" && !window.location.search) return;
    history[push ? "pushState" : "replaceState"]({}, "", "/");
  }

  /* ── Small helpers ──────────────────────────────────────── */

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function setThumb(container, source, alt = "") {
    if (!container) return;
    container.replaceChildren();
    if (source) {
      const image = document.createElement("img");
      image.src = source;
      image.alt = alt;
      image.loading = "lazy";
      container.append(image);
    } else {
      container.innerHTML = FILM_ICON;
    }
  }

  function formatBytes(bytes) {
    if (!bytes || bytes < 0) return "0 MB";
    const units = ["B", "KB", "MB", "GB"];
    let value = Number(bytes);
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    const precision = unit <= 1 || value >= 100 ? 0 : 1;
    return `${value.toFixed(precision)} ${units[unit]}`;
  }

  function formatClock(seconds, { round = false } = {}) {
    const numeric = Number(seconds);
    if (!Number.isFinite(numeric) || numeric < 0) return "0:00";
    let total = round ? Math.round(numeric) : Math.floor(numeric);
    const hours = Math.floor(total / 3600);
    total %= 3600;
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    return hours > 0
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
      : `${minutes}:${String(secs).padStart(2, "0")}`;
  }

  function formatElapsed(startMs) {
    const seconds = Math.max(0, (Date.now() - startMs) / 1000);
    if (seconds < 2) return "Just starting";
    return `${formatClock(seconds)} elapsed`;
  }

  function platformLimit(platform) {
    const found = state.platformOptions.find((item) => item.value === platform);
    return found?.limit || 2200;
  }

  function platformLabel(platform) {
    const found = state.platformOptions.find((item) => item.value === platform);
    return found?.label || "Instagram";
  }

  function toneLabel(tone) {
    return state.toneOptions.find((item) => item.value === tone)?.label || "Auto";
  }

  function slugify(value) {
    return String(value || "scenescribe")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-zA-Z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase()
      .slice(0, 54) || "scenescribe";
  }

  function showToast(message) {
    if (!message) return;
    dom.toastText.textContent = message;
    dom.toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      dom.toast.classList.remove("is-visible");
    }, 3400);
  }

  function showUploadError(message) {
    dom.uploadError.textContent = message;
    dom.uploadError.hidden = false;
  }

  function clearUploadError() {
    dom.uploadError.textContent = "";
    dom.uploadError.hidden = true;
  }

  async function readResponse(response) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      try {
        const text = await response.text();
        if (text.trim()) payload = { error: text.trim().slice(0, 240) };
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      const error = new Error(payload?.error || `The local studio returned ${response.status}.`);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload || {};
  }

  async function copyText(value) {
    const text = String(value ?? "");
    if (!text) return false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // Fall through to the older selection-based copy.
    }
    try {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.top = "-1000px";
      helper.style.opacity = "0";
      document.body.append(helper);
      helper.select();
      const copied = document.execCommand("copy");
      helper.remove();
      return copied;
    } catch {
      return false;
    }
  }

  /* ── File selection & preview ──────────────────────────── */

  function validateFile(file) {
    if (!file) return "Choose a video file first.";
    if (!file.size) return "That file is empty. Pick an exported video.";
    const extension = (file.name.split(".").pop() || "").toLowerCase();
    const mime = (file.type || "").toLowerCase();
    if (!ALLOWED_EXTENSIONS.has(extension) && !MIME_EXTENSIONS.has(mime)) {
      return "Unsupported file type. Use MP4, MOV, M4V, WEBM, MKV, or AVI.";
    }
    const limitMb = Number(state.health?.max_upload_mb) || 500;
    if (file.size > limitMb * 1024 * 1024) {
      return `That file is ${formatBytes(file.size)}. The local limit is ${limitMb} MB.`;
    }
    return null;
  }

  function selectFile(file) {
    const problem = validateFile(file);
    if (problem) {
      showUploadError(problem);
      dom.fileInput.value = "";
      return;
    }

    clearUploadError();
    state.file = file;
    state.inspection = null;

    dom.dropzone.classList.add("has-file");
    dom.dropIdle.hidden = true;
    dom.filePreview.hidden = false;
    dom.fileName.textContent = file.name;
    dom.fileMeta.textContent = `${formatBytes(file.size)} · Reading preview…`;
    setThumb(dom.fileThumb, null);
    dom.readButton.disabled = false;
    dom.readButtonLabel.textContent = "Read this video";
    dom.fileInput.value = "";

    inspectVideoFile(file).then((info) => {
      if (state.file !== file) return;
      state.inspection = info;
      updateFilePreview();
      if (state.mode === "process") configureProcessFileFromFile(file);
    });
  }

  function updateFilePreview() {
    if (!state.file) return;
    const info = state.inspection;
    if (info) {
      const duration = Number.isFinite(info.duration) ? `${formatClock(info.duration, { round: true })} · ` : "";
      const size = Number.isFinite(info.width) && Number.isFinite(info.height)
        ? `${info.width} × ${info.height} · `
        : "";
      dom.fileMeta.textContent = `${duration}${size}${formatBytes(state.file.size)}`;
      if (info.thumb) setThumb(dom.fileThumb, info.thumb);
    } else {
      dom.fileMeta.textContent = `${formatBytes(state.file.size)} · Ready to read`;
    }
  }

  function inspectVideoFile(file) {
    return new Promise((resolve) => {
      const video = document.createElement("video");
      const url = URL.createObjectURL(file);
      let settled = false;
      let metadata = null;
      let timer = null;

      const finish = (value) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        video.onloadedmetadata = null;
        video.onseeked = null;
        video.onerror = null;
        try {
          video.removeAttribute("src");
          video.load();
        } catch {
          // The preview is optional; ignore teardown quirks.
        }
        URL.revokeObjectURL(url);
        resolve(value);
      };

      video.preload = "metadata";
      video.muted = true;
      video.playsInline = true;

      video.onloadedmetadata = () => {
        const duration = Number(video.duration);
        const width = Number(video.videoWidth) || 0;
        const height = Number(video.videoHeight) || 0;
        metadata = {
          duration: Number.isFinite(duration) ? duration : 0,
          width,
          height,
          thumb: null
        };

        if (!Number.isFinite(duration) || duration <= 0.05 || !width || !height) {
          finish(metadata);
          return;
        }

        const target = Math.min(Math.max(duration * 0.12, 0.08), Math.max(0.08, duration - 0.08));
        try {
          video.currentTime = target;
        } catch {
          finish(metadata);
        }
      };

      video.onseeked = () => {
        if (!metadata) return;
        try {
          const scale = Math.min(1, 720 / Math.max(metadata.width, 1));
          const canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(metadata.width * scale));
          canvas.height = Math.max(1, Math.round(metadata.height * scale));
          const context = canvas.getContext("2d");
          if (!context) {
            finish(metadata);
            return;
          }
          context.drawImage(video, 0, 0, canvas.width, canvas.height);
          metadata.thumb = canvas.toDataURL("image/jpeg", 0.76);
          finish(metadata);
        } catch {
          finish(metadata);
        }
      };

      video.onerror = () => finish(metadata);
      timer = window.setTimeout(() => finish(metadata), 7000);
      video.src = url;
    });
  }

  function clearSelectedFile({ focus = false } = {}) {
    state.file = null;
    state.inspection = null;
    dom.fileInput.value = "";
    dom.dropzone.classList.remove("has-file");
    dom.filePreview.hidden = true;
    dom.dropIdle.hidden = false;
    dom.fileName.textContent = "video.mp4";
    dom.fileMeta.textContent = "Preparing preview…";
    setThumb(dom.fileThumb, null);
    dom.readButton.disabled = true;
    dom.readButton.classList.remove("is-uploading");
    dom.readButtonLabel.textContent = "Read this video";
    clearUploadError();
    if (focus) dom.dropzone.focus({ preventScroll: true });
  }

  /* ── Process file summary ───────────────────────────────── */

  function setProcessFile(name, meta, thumbSource) {
    dom.processFileName.textContent = name || "Your video";
    dom.processFileMeta.textContent = meta || "";
    setThumb(dom.processThumb, thumbSource);
  }

  function configureProcessFileFromFile(file) {
    if (!file) {
      setProcessFile("Your video", "Preparing the read", null);
      return;
    }
    const info = state.inspection;
    const dimensions = info && info.width && info.height ? `${info.width} × ${info.height} · ` : "";
    const duration = info && Number.isFinite(info.duration) && info.duration > 0
      ? `${formatClock(info.duration, { round: true })} · `
      : "";
    setProcessFile(
      file.name,
      `${duration}${dimensions}${formatBytes(file.size)}`,
      info?.thumb || null
    );
  }

  function prepareLoadingProcess() {
    hideProcessError();
    dom.processView.classList.remove("is-error");
    state.currentStageIndex = 0;
    setProcessFile("Loading the edit", "Reading from this device", null);
    updateProcessUI({ stageKey: "probe", overall: 3, message: "Opening the saved read" });
    setView("process", { focus: false });
    startElapsed(Date.now());
  }

  /* ── Upload ─────────────────────────────────────────────── */

  function startUpload() {
    if (!state.file) {
      showUploadError("Choose a video file first.");
      return;
    }

    if (state.health && (!state.health.ffmpeg || !state.health.ffprobe)) {
      showUploadError("The local video engine is unavailable. Install ffmpeg, or set SCENESCRIBE_FFMPEG and SCENESCRIBE_FFPROBE, then restart the studio.");
      return;
    }

    clearUploadError();
    hideProcessError();
    dom.processView.classList.remove("is-error");
    abortUpload();

    state.jobId = null;
    state.job = null;
    state.result = null;
    state.captionSet = null;
    state.captions = [];
    state.selectedId = null;
    state.editingId = null;
    state.seed = 0;
    state.currentStageIndex = 0;

    configureProcessFileFromFile(state.file);
    setView("process");
    updateProcessUI({
      stageKey: "upload",
      overall: 0,
      message: "Sending the edit to the local studio"
    });
    startElapsed(Date.now());

    dom.readButton.disabled = true;
    dom.readButton.classList.add("is-uploading");
    dom.readButtonLabel.textContent = "Sending…";

    const form = new FormData();
    form.append("video", state.file, state.file.name);
    form.append("tone", "auto");
    form.append("platform", "instagram");

    const xhr = new XMLHttpRequest();
    state.uploadXhr = xhr;
    xhr.open("POST", "/api/analyze");
    xhr.responseType = "json";

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable || !event.total) return;
      const percent = Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100)));
      const overall = Math.min(9, Math.round(percent * 0.09));
      updateProcessUI({
        stageKey: "upload",
        overall,
        message: percent >= 100 ? "Upload complete — opening the cut" : `Uploading the cut — ${percent}%`
      });
    });

    xhr.addEventListener("load", () => {
      if (state.uploadXhr !== xhr) return;
      state.uploadXhr = null;
      const payload = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300 && payload?.id) {
        handleUploadAccepted(payload);
        return;
      }
      const message = payload?.error
        || `The upload stopped unexpectedly (${xhr.status || "no response"}).`;
      handleStartFailure(message);
    });

    xhr.addEventListener("error", () => {
      if (state.uploadXhr !== xhr) return;
      state.uploadXhr = null;
      handleStartFailure("The upload couldn’t reach the local studio. Is the server still running?");
    });

    xhr.addEventListener("abort", () => {
      if (state.uploadXhr === xhr) state.uploadXhr = null;
    });

    xhr.send(form);
  }

  function handleUploadAccepted(payload) {
    state.jobId = payload.id;
    state.job = payload;
    updateUrlForJob(payload.id, { push: true });
    state.currentStageIndex = 0;
    dom.readButton.classList.remove("is-uploading");
    dom.readButtonLabel.textContent = "Read this video";
    updateProcessUI({
      stageKey: "probe",
      overall: 10,
      message: "Queued — opening the cut"
    });
    const name = state.file?.name || "your video";
    document.title = `Reading ${name} — SceneScribe`;
    startElapsed(Date.now());
    startPolling();
  }

  function handleStartFailure(message) {
    state.uploadXhr = null;
    dom.readButton.classList.remove("is-uploading");
    dom.readButtonLabel.textContent = "Read this video";
    dom.readButton.disabled = !state.file;
    showProcessError(message, {
      retryLabel: state.file ? "Try again" : null,
      retry: state.file ? () => startUpload() : null
    });
  }

  function abortUpload() {
    if (!state.uploadXhr) return;
    const xhr = state.uploadXhr;
    state.uploadXhr = null;
    try {
      xhr.abort();
    } catch {
      // Nothing to clean up.
    }
  }

  function resetToLanding({ focusUpload = false, pushHistory = true } = {}) {
    stopPolling();
    stopElapsed();
    stopClipPolling();
    stopForgeElapsed();
    abortUpload();

    state.jobId = null;
    state.job = null;
    state.result = null;
    state.captionSet = null;
    state.captions = [];
    state.selectedId = null;
    state.editingId = null;
    state.seed = 0;
    state.currentStageIndex = 0;
    state.frames = [];
    state.activeFrame = -1;
    state.clipRunId = null;
    state.clipRun = null;
    state.forgeSubmitting = false;
    state.forgeCaptionBusy = false;

    clearSelectedFile();
    hideProcessError();
    dom.processView.classList.remove("is-error");
    dom.forgeView.classList.remove("is-running", "is-results");
    dom.forgeWorkspace.hidden = false;
    dom.forgeProgress.hidden = true;
    dom.forgeResults.hidden = true;
    dom.studioDeckLink.hidden = true;
    dom.toneSelect.value = "auto";
    dom.platformSelect.value = "instagram";
    state.tone = "auto";
    state.platform = "instagram";

    try {
      dom.videoPlayer.pause();
      dom.videoPlayer.removeAttribute("src");
      dom.videoPlayer.load();
    } catch {
      // The player may not have been initialised yet.
    }

    if (pushHistory) clearJobUrl({ push: true });
    setView("landing", { focus: false });
    document.title = HOME_TITLE;

    if (focusUpload) {
      window.setTimeout(() => {
        dom.upload.scrollIntoView({ behavior: "smooth", block: "start" });
        dom.dropzone.focus({ preventScroll: true });
      }, 30);
    } else {
      window.scrollTo({ top: 0, behavior: "auto" });
    }
  }

  /* ── Processing state ───────────────────────────────────── */

  function updateProcessUI({ stageKey, overall, message }) {
    const percent = Math.max(0, Math.min(100, Math.round(Number(overall) || 0)));
    dom.processPercent.textContent = `${percent}%`;
    dom.progressFill.style.width = `${percent}%`;
    dom.progressBar.setAttribute("aria-valuenow", String(percent));
    if (message) dom.processMessage.textContent = message;

    const index = STAGE_ORDER.indexOf(stageKey);
    const safeIndex = index >= 0 ? index : 1;
    state.currentStageIndex = Math.max(state.currentStageIndex, safeIndex);
    const complete = percent >= 100;

    dom.stageItems.forEach((item, itemIndex) => {
      const key = item.dataset.stage;
      const isDone = complete || itemIndex < state.currentStageIndex;
      const isActive = !complete && itemIndex === state.currentStageIndex;
      item.classList.toggle("is-done", isDone);
      item.classList.toggle("is-active", isActive);
      const status = item.querySelector(".stage-state");
      if (!status) return;
      if (complete || isDone) {
        status.textContent = "Done";
      } else if (isActive) {
        status.textContent = STAGE_STATES[key] || "Reading";
      } else {
        status.textContent = "Waiting";
      }
    });
  }

  function startElapsed(startMs) {
    stopElapsed();
    const numeric = Number(startMs);
    state.processStarted = Number.isFinite(numeric) && numeric > 0
      ? Math.min(numeric, Date.now())
      : Date.now();
    const update = () => {
      dom.processElapsed.textContent = formatElapsed(state.processStarted);
    };
    update();
    state.elapsedTimer = window.setInterval(update, 1000);
  }

  function stopElapsed() {
    if (!state.elapsedTimer) return;
    window.clearInterval(state.elapsedTimer);
    state.elapsedTimer = null;
  }

  function startPolling() {
    stopPolling();
    state.pollFailures = 0;
    schedulePoll(420);
  }

  function schedulePoll(delay) {
    stopPolling();
    state.pollTimer = window.setTimeout(pollOnce, delay);
  }

  function stopPolling() {
    if (!state.pollTimer) return;
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }

  async function pollOnce() {
    state.pollTimer = null;
    if (state.mode !== "process" || !state.jobId) return;
    const jobId = state.jobId;

    try {
      const response = await fetch(`/api/jobs/${jobId}`, {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error(payload?.error || `The local studio returned ${response.status}.`);
        error.status = response.status;
        throw error;
      }
      const job = await response.json();
      if (state.jobId !== jobId || state.mode !== "process") return;
      state.pollFailures = 0;
      state.job = job;

      if (job.status === "complete" && job.result) {
        finishJob(job);
        return;
      }
      if (job.status === "error") {
        showProcessError(job.error || "Something went wrong while reading this video. Try another export or a shorter clip.");
        return;
      }

      applyProcessingJob(job);
      schedulePoll(1000);
    } catch (error) {
      if (state.jobId !== jobId || state.mode !== "process") return;
      state.pollFailures += 1;

      if (error.status === 404) {
        showProcessError("This read is no longer available. The local server may have restarted before the result was saved.");
        return;
      }

      if (state.pollFailures >= 5) {
        showProcessError("Lost the connection to the local studio. The read may still be running — check again in a moment.", {
          retryLabel: "Check again",
          retry: () => openJob(jobId)
        });
        return;
      }

      schedulePoll(1100 + state.pollFailures * 550);
    }
  }

  function applyProcessingJob(job) {
    const stage = STAGE_ORDER.includes(job.stage) && job.stage !== "queued" ? job.stage : "probe";
    const progress = Number(job.progress) || 0;
    const overall = Math.min(99, 10 + Math.round(progress * 0.9));
    const name = job.original_name || state.file?.name;
    if (name && state.mode === "process") {
      const thumb = state.file && state.file.name === name ? state.inspection?.thumb : null;
      const meta = state.file ? "" : "Reading on this device";
      if (dom.processFileName.textContent !== name) {
        setProcessFile(name, meta, thumb || null);
      } else if (meta) {
        dom.processFileMeta.textContent = meta;
      }
      document.title = `Reading ${name} — SceneScribe`;
    }
    updateProcessUI({
      stageKey: stage,
      overall,
      message: job.message || "Reading the cut"
    });
  }

  function finishJob(job) {
    if (!job?.result) {
      showProcessError("The read finished without a result. Try reading the video again.");
      return;
    }
    stopPolling();
    updateProcessUI({ stageKey: "write", overall: 100, message: "Your captions are ready" });
    stopElapsed();
    const id = job.id || state.jobId;
    if (id) {
      state.jobId = id;
      updateUrlForJob(id, { push: false });
    }
    state.job = job;
    renderStudio(job.result, job);
    setView("studio");
  }

  function showProcessError(message, { retryLabel = null, retry = null } = {}) {
    stopPolling();
    stopElapsed();
    state.errorRetryHandler = retry;
    dom.processError.hidden = false;
    dom.processErrorText.textContent = message;
    dom.errorRetry.hidden = !retry;
    dom.errorRetry.textContent = retryLabel || "Check again";
    dom.processView.classList.add("is-error");
    dom.processMessage.textContent = "The read stopped short.";
    dom.processError.setAttribute("tabindex", "-1");
    requestAnimationFrame(() => {
      dom.processError.focus({ preventScroll: true });
    });
  }

  function hideProcessError() {
    dom.processError.hidden = true;
    dom.errorRetry.hidden = true;
    state.errorRetryHandler = null;
    dom.processView.classList.remove("is-error");
  }

  /* ── Deep links & resuming ───────────────────────────────── */

  async function openJob(jobId, { fromLink = false } = {}) {
    if (!JOB_ID_RE.test(jobId || "")) {
      history.replaceState({}, "", "/");
      setView("landing", { focus: false });
      showToast("That result link doesn’t look right.");
      return;
    }

    stopPolling();
    stopElapsed();
    abortUpload();
    hideProcessError();

    state.jobId = jobId;
    state.job = null;
    state.result = null;
    state.captionSet = null;
    state.captions = [];
    state.selectedId = null;
    state.editingId = null;
    state.seed = 0;
    state.currentStageIndex = 0;

    if (state.mode !== "process") {
      setProcessFile("Loading the edit", "Reading from this device", null);
      updateProcessUI({ stageKey: "probe", overall: 3, message: "Opening the saved read" });
      setView("process", { focus: false });
      startElapsed(Date.now());
    }

    try {
      const response = await fetch(`/api/jobs/${jobId}`, {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error(payload?.error || `The local studio returned ${response.status}.`);
        error.status = response.status;
        throw error;
      }

      const job = await response.json();
      if (state.jobId !== jobId) return;
      state.job = job;
      state.jobId = job.id || jobId;

      const thumb = state.file && state.file.name === job.original_name ? state.inspection?.thumb : null;
      if (job.original_name) {
        setProcessFile(job.original_name, job.status === "complete" ? "Read locally" : "Reading on this device", thumb);
        document.title = `Reading ${job.original_name} — SceneScribe`;
      }

      if (job.status === "complete" && job.result) {
        finishJob(job);
        return;
      }

      if (job.status === "error") {
        showProcessError(job.error || "Something went wrong while reading this video. Try another export or a shorter clip.");
        return;
      }

      const started = Date.parse(job.created_at || "");
      startElapsed(Number.isFinite(started) ? started : Date.now());
      applyProcessingJob(job);
      startPolling();
    } catch (error) {
      if (error.status === 404) {
        state.jobId = null;
        stopElapsed();
        if (state.clipRunId && CLIP_RUN_ID_RE.test(state.clipRunId)) {
          const runId = state.clipRunId;
          showToast("That saved read has expired. The clip deck is still here.");
          openClipRun(runId, { push: false });
          return;
        }
        history.replaceState({}, "", "/");
        setView("landing", { focus: false });
        showToast(fromLink
          ? "That read has expired, moved, or was never saved."
          : "That read could not be found on this device.");
        return;
      }
      showProcessError("The local studio didn’t answer. Make sure the server is still running, then try again.", {
        retryLabel: "Check again",
        retry: () => openJob(jobId, { fromLink })
      });
    }
  }

  /* ── Studio rendering ──────────────────────────────────── */

  function renderStudio(result, job) {
    const analysis = result?.analysis || {};
    const video = analysis.video || {};
    const reading = analysis.reading || {};
    const context = analysis.caption_context || {};
    const captionSet = result?.caption_set || {};

    state.result = result;
    state.job = job || state.job;
    state.captionSet = captionSet;
    state.captions = Array.isArray(captionSet.captions) ? captionSet.captions.slice() : [];
    state.seed = Number(captionSet.seed) || 0;
    state.editingId = null;
    state.activeFrame = -1;
    state.frames = Array.isArray(analysis.frames) ? analysis.frames : [];

    if (!state.captions.some((caption) => caption.id === state.selectedId)) {
      state.selectedId = captionSet.recommended_id
        || state.captions.find((caption) => caption.recommended)?.id
        || state.captions[0]?.id
        || null;
    }

    const displayName = video.display_name || "Your video";
    document.title = `${displayName} — SceneScribe`;
    dom.studioTitle.textContent = displayName;
    dom.studioTitle.title = video.filename || displayName;
    renderMeta(video, context);

    const origin = job?.origin;
    const originRunId = origin?.kind === "clipforge" && CLIP_RUN_ID_RE.test(origin.run_id || "")
      ? origin.run_id
      : null;
    if (originRunId) {
      state.clipRunId = originRunId;
      const chip = element(
        "span",
        "meta-chip meta-chip--origin",
        `ClipForge · ${origin.label || "clip"}`
      );
      chip.title = "This read came from a ClipForge clip deck.";
      dom.studioMeta.prepend(chip);
      dom.studioDeckLink.hidden = false;
      dom.studioDeckLink.href = `/?clips=${encodeURIComponent(originRunId)}`;
    } else {
      state.clipRunId = null;
      dom.studioDeckLink.hidden = true;
      dom.studioDeckLink.href = "/";
    }

    if (video.video_url) {
      dom.videoPlayer.src = video.video_url;
      dom.videoPlayer.poster = video.poster_url || "";
    }
    dom.downloadVideo.href = video.download_url || video.video_url || "#";
    dom.downloadVideo.removeAttribute("download");

    dom.videoFrame.classList.toggle("is-vertical", video.orientation_key === "vertical");
    dom.videoFrame.classList.toggle("is-square", video.orientation_key === "square");

    const pace = reading.pace || {};
    dom.videoPace.textContent = pace.label
      ? `${pace.label}${pace.average_shot_seconds ? ` · ${Number(pace.average_shot_seconds).toFixed(1)}s` : ""}`
      : "The read";

    renderFrames(state.frames);
    renderPalette(reading.palette || context.palette || []);
    renderSpecs(video, analysis.audio || {}, reading);

    dom.moodBadge.textContent = reading.mood?.label || "The read";
    dom.readSummary.textContent = reading.summary || context.summary || "";
    renderSignals(reading.insights || []);
    renderQuote(reading.quote || context.quote || null);
    renderKeywords(reading.keywords || context.keywords || [], reading.brand || context.brand || "");
    renderOnscreen(analysis.onscreen || {});
    renderTranscript(analysis.transcript || {});
    renderWarnings(result?.warnings || job?.warnings || []);

    syncSelectsFromCaptionSet(captionSet);
    renderCaptions(captionSet);

    dom.generatedLabel.textContent = formatGenerated(result?.generated_at || job?.completed_at);
    dom.generatedLabel.title = result?.generated_at || job?.completed_at || "";
  }

  function renderMeta(video, context) {
    dom.studioMeta.replaceChildren();
    const add = (text, strong = false) => {
      if (!text) return;
      dom.studioMeta.append(element("span", `meta-chip${strong ? " meta-chip--strong" : ""}`, text));
    };
    add(context.topic_label || "Video read", true);
    add(video.duration_sentence || video.duration_label);
    if (video.width && video.height) add(`${video.width} × ${video.height}`);
    add(video.orientation);
    if (video.fps) add(`${Number(video.fps).toFixed(video.fps % 1 ? 1 : 0)} fps`);
    add(video.size_label);
  }

  function renderFrames(frames) {
    dom.frameRail.replaceChildren();
    state.frames = frames;
    if (!frames.length) {
      dom.frameCount.textContent = "No frames";
      dom.frameRail.append(element("p", "detail-empty", "No frames were saved for this read."));
      return;
    }

    const cuts = frames.filter((frame) => frame.is_transition).length;
    dom.frameCount.textContent = `${frames.length} frames · ${cuts} cut${cuts === 1 ? "" : "s"}`;

    frames.forEach((frame, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "frame-button";
      button.dataset.index = String(index);
      button.setAttribute(
        "aria-label",
        `Jump to frame ${index + 1} at ${frame.time_label || formatClock(frame.time)}${frame.is_transition ? ", after a cut" : ""}`
      );
      button.title = `Frame ${index + 1} · ${frame.time_label || formatClock(frame.time)}`;

      const image = document.createElement("img");
      image.src = frame.url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";

      const time = element("span", "frame-time", frame.time_label || formatClock(frame.time));
      button.append(image, time);

      if (frame.is_transition) {
        button.append(element("span", "frame-cut", "cut"));
      }

      button.addEventListener("click", () => seekToFrame(index));
      dom.frameRail.append(button);
    });
  }

  function seekToFrame(index) {
    const frame = state.frames[index];
    if (!frame) return;
    try {
      dom.videoPlayer.currentTime = Math.max(0, Number(frame.time) || 0);
      const playback = dom.videoPlayer.play();
      if (playback && typeof playback.catch === "function") playback.catch(() => {});
    } catch {
      // Seeking is a convenience; playback controls still work.
    }
    setActiveFrame(index);
  }

  function setActiveFrame(index) {
    if (index === state.activeFrame) return;
    state.activeFrame = index;
    dom.frameRail.querySelectorAll(".frame-button").forEach((button, buttonIndex) => {
      button.classList.toggle("is-active", buttonIndex === index);
    });
  }

  function syncFrameHighlight() {
    if (!state.frames.length) return;
    const time = Number(dom.videoPlayer.currentTime) || 0;
    let best = 0;
    let bestDistance = Infinity;
    state.frames.forEach((frame, index) => {
      const distance = Math.abs((Number(frame.time) || 0) - time);
      if (distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    });
    setActiveFrame(best);
  }

  function renderPalette(palette) {
    dom.paletteList.replaceChildren();
    const usable = (Array.isArray(palette) ? palette : []).filter((item) => item && item.hex).slice(0, 4);
    if (!usable.length) {
      dom.paletteList.append(element("span", "detail-empty", "No dominant colour read."));
      return;
    }
    usable.forEach((color) => {
      const item = element("div", "palette-item");
      item.title = `${color.name || "Colour"} · ${color.hex}${color.role ? ` · ${color.role}` : ""}`;
      const chip = element("span", "palette-chip");
      if (/^#[0-9a-f]{6}$/i.test(color.hex)) chip.style.backgroundColor = color.hex;
      const copy = element("span", "palette-copy");
      copy.append(
        element("strong", null, color.name || "Colour"),
        element("span", null, String(color.hex || "").toUpperCase())
      );
      item.append(chip, copy);
      dom.paletteList.append(item);
    });
  }

  function renderSpecs(video, audio, reading) {
    dom.specs.replaceChildren();
    const add = (label, value) => {
      if (!value) return;
      const spec = element("div", "spec");
      spec.append(element("span", null, label), element("strong", null, value));
      dom.specs.append(spec);
    };
    add("Codec", video.video_codec || "Video");
    add("Audio", video.has_audio ? (video.audio_codec || "Audio") : "Silent");
    add("Size", video.size_label);
    add("Mix", audio.character || reading.sound?.label);
  }

  function renderSignals(insights) {
    dom.signalGrid.replaceChildren();
    const items = (Array.isArray(insights) ? insights : []).slice(0, 4);
    if (!items.length) {
      dom.signalGrid.append(element("p", "detail-empty", "The read is still taking shape."));
      return;
    }
    items.forEach((insight) => {
      const card = element("div", "signal-card");
      card.append(
        element("span", "signal-label", insight.label || "Read"),
        element("strong", "signal-value", insight.value || "—"),
        element("span", "signal-detail", insight.detail || "")
      );
      dom.signalGrid.append(card);
    });
  }

  function renderQuote(quote) {
    const text = String(quote?.text || "").trim();
    if (!text) {
      dom.quoteBlock.hidden = true;
      dom.quoteText.textContent = "";
      dom.quoteSource.textContent = "";
      return;
    }
    dom.quoteBlock.hidden = false;
    dom.quoteText.textContent = text;
    const source = [quote.source_label || "From the video", quote.time_label]
      .filter(Boolean)
      .join(" · ");
    dom.quoteSource.textContent = source;
  }

  function renderKeywords(keywords, brand) {
    dom.keywordRow.replaceChildren();
    const block = dom.keywordRow.closest(".keyword-block");
    const seen = new Set();
    const ordered = [];

    const push = (word) => {
      const clean = String(word || "").trim();
      const key = clean.toLowerCase();
      if (!clean || seen.has(key)) return;
      seen.add(key);
      ordered.push(clean);
    };

    push(brand);
    (Array.isArray(keywords) ? keywords : []).forEach(push);

    if (!ordered.length) {
      if (block) block.hidden = true;
      return;
    }
    if (block) block.hidden = false;

    ordered.slice(0, 10).forEach((word) => {
      const chip = element("span", "keyword", word);
      if (brand && word.toLowerCase() === String(brand).toLowerCase()) {
        chip.classList.add("keyword--brand");
      }
      dom.keywordRow.append(chip);
    });
  }

  function renderOnscreen(onscreen) {
    const lines = Array.isArray(onscreen.lines) ? onscreen.lines : [];
    dom.onscreenCount.textContent = lines.length
      ? `${lines.length} line${lines.length === 1 ? "" : "s"}`
      : onscreen.available
        ? "None found"
        : "Unavailable";
    dom.onscreenList.replaceChildren();

    if (!lines.length) {
      dom.onscreenList.append(element(
        "p",
        "detail-empty",
        onscreen.reason || "No on-screen text was clear enough to read."
      ));
      return;
    }

    lines.slice(0, 14).forEach((line) => {
      const row = element("div", "onscreen-line");
      row.append(element("span", "line-time", line.time_label || formatClock(line.time)));
      const copy = element("div", "line-copy", line.text || "");
      const confidence = Number(line.confidence);
      const meta = [];
      if (Number.isFinite(confidence)) meta.push(`${Math.round(confidence * 100)}% confidence`);
      if (Number(line.occurrences) > 1) meta.push(`seen ${line.occurrences}×`);
      if (meta.length) copy.append(element("small", null, meta.join(" · ")));
      row.append(copy);
      dom.onscreenList.append(row);
    });

    if (lines.length > 14) {
      dom.onscreenList.append(element("p", "detail-empty", `Plus ${lines.length - 14} more lines.`));
    }
  }

  function renderTranscript(transcript) {
    const available = Boolean(transcript.available);
    const segments = Array.isArray(transcript.segments) ? transcript.segments : [];
    const language = String(transcript.language || "").toUpperCase();
    const probability = Number(transcript.language_probability);

    dom.transcriptQuality.textContent = available
      ? transcript.quote_ready ? "Clear" : "Unclear"
      : "No speech";
    dom.transcriptList.replaceChildren();

    if (!available) {
      dom.transcriptList.append(element(
        "p",
        "detail-empty",
        transcript.reason || "No usable speech was found in this edit."
      ));
      return;
    }

    const note = element("p", "detail-empty");
    if (!transcript.quote_ready) {
      note.textContent = "Speech was heard, but not confidently enough to lead the caption. Here’s what came through:";
    } else if (language) {
      note.textContent = `Detected ${language}${Number.isFinite(probability) ? ` · ${Math.round(probability * 100)}% confidence` : ""}.`;
    } else {
      note.textContent = "The voice in this edit came through clearly.";
    }
    dom.transcriptList.append(note);

    if (segments.length) {
      segments.slice(0, MAX_SEGMENTS).forEach((segment) => {
        const row = element("div", "transcript-segment");
        row.append(element("span", "line-time", formatClock(segment.start)));
        row.append(element("p", null, segment.text || ""));
        dom.transcriptList.append(row);
      });
      if (segments.length > MAX_SEGMENTS) {
        dom.transcriptList.append(element(
          "p",
          "detail-empty",
          `Plus ${segments.length - MAX_SEGMENTS} more segment${segments.length - MAX_SEGMENTS === 1 ? "" : "s"}.`
        ));
      }
    } else if (transcript.text) {
      dom.transcriptList.append(element("p", "transcript-text", transcript.text));
    } else {
      dom.transcriptList.append(element("p", "detail-empty", "No words were clear enough to keep."));
    }
  }

  function renderWarnings(warnings) {
    const list = (Array.isArray(warnings) ? warnings : []).filter(Boolean);
    dom.warningText.replaceChildren();
    if (!list.length) {
      dom.warningNote.hidden = true;
      return;
    }
    dom.warningNote.hidden = false;
    list.forEach((warning) => {
      dom.warningText.append(element("p", null, warning));
    });
  }

  function formatGenerated(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    try {
      const formatted = new Intl.DateTimeFormat(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      }).format(date);
      return `Read ${formatted}`;
    } catch {
      return `Read ${date.toLocaleString()}`;
    }
  }

  function updateToneNote(captionSet) {
    if (!captionSet) return;
    const tone = captionSet.tone_label || toneLabel(captionSet.tone);
    const platform = captionSet.platform_label || platformLabel(captionSet.platform);
    const description = String(captionSet.tone_description || "").trim();
    const soft = description
      ? `${description.charAt(0).toLowerCase()}${description.slice(1)}`
      : "";
    const lead = captionSet.tone_auto
      ? `Auto picked ${tone} for this cut`
      : `${tone} tone`;
    dom.toneNote.textContent = `${lead}${soft ? ` — ${soft}` : ""} Shaped for ${platform}.`;
  }

  /* ── Caption workspace ──────────────────────────────────── */

  function syncSelectsFromCaptionSet(captionSet) {
    if (!captionSet) return;
    const requested = captionSet.tone_requested === "auto"
      ? "auto"
      : captionSet.tone_requested
        || (captionSet.tone_auto ? "auto" : captionSet.tone)
        || "auto";
    state.tone = requested;
    state.platform = captionSet.platform || state.platform || "instagram";
    state.seed = Number(captionSet.seed) || 0;
    if ([...dom.toneSelect.options].some((option) => option.value === state.tone)) {
      dom.toneSelect.value = state.tone;
    }
    if ([...dom.platformSelect.options].some((option) => option.value === state.platform)) {
      dom.platformSelect.value = state.platform;
    }
  }

  function renderCaptions(captionSet) {
    if (!captionSet) return;
    state.captionSet = captionSet;
    state.captions = Array.isArray(captionSet.captions) ? captionSet.captions.slice() : [];

    if (!state.captions.some((caption) => caption.id === state.selectedId)) {
      state.selectedId = captionSet.recommended_id
        || state.captions.find((caption) => caption.recommended)?.id
        || state.captions[0]?.id
        || null;
    }

    syncSelectsFromCaptionSet(captionSet);
    dom.captionGrid.replaceChildren();

    if (!state.captions.length) {
      dom.captionGrid.append(element("p", "detail-empty", "No captions were written for this read."));
      updateSelectionUI();
      return;
    }

    state.captions.forEach((caption, index) => {
      dom.captionGrid.append(createCaptionCard(caption, index));
    });

    updateToneNote(captionSet);
    updateSelectionUI();
  }

  function createCaptionCard(caption, index) {
    const selected = caption.id === state.selectedId;
    const editing = caption.id === state.editingId;
    const limit = platformLimit(state.captionSet?.platform || state.platform);

    const card = element("article", `caption-card${selected ? " is-selected" : ""}`);
    card.dataset.id = caption.id;

    const top = element("div", "card-top");
    top.append(element("span", "card-index", String(index + 1).padStart(2, "0")));

    const heading = element("div", "card-heading");
    heading.append(
      element("h3", null, caption.label || "Caption"),
      element("p", null, caption.note || "")
    );
    top.append(heading);
    if (caption.recommended) top.append(element("span", "rec-badge", "Recommended"));
    card.append(top);

    if (editing) {
      const editor = document.createElement("textarea");
      editor.className = "card-editor";
      editor.value = caption.body || "";
      editor.rows = 6;
      editor.setAttribute("aria-label", `Edit the ${caption.label || "caption"} text`);
      card.append(editor);
    } else {
      card.append(element("p", "card-copy", caption.body || ""));
    }

    const tags = Array.isArray(caption.hashtags) ? caption.hashtags : [];
    if (tags.length) {
      const tagRow = element("div", "card-tags");
      tags.forEach((tag) => tagRow.append(element("span", "card-tag", tag)));
      card.append(tagRow);
    }

    const footer = element("div", "card-foot");
    const body = editing ? caption.body || "" : caption.body || "";
    const count = composeFullText(body, tags, state.captionSet?.platform || state.platform).length;
    const countNode = element("span", `char-count${count > limit ? " is-over" : ""}`, `${count.toLocaleString()} chars`);
    footer.append(countNode);

    const actions = element("div", "card-actions");
    if (editing) {
      const save = element("button", "card-button is-save", "Save");
      save.type = "button";
      save.dataset.action = "save";
      const cancel = element("button", "card-button", "Cancel");
      cancel.type = "button";
      cancel.dataset.action = "cancel";
      actions.append(save, cancel);
    } else {
      const use = element("button", "card-button is-use", selected ? "Selected" : "Use");
      use.type = "button";
      use.dataset.action = "use";
      use.setAttribute("aria-pressed", String(selected));
      const copy = element("button", "card-button", "Copy");
      copy.type = "button";
      copy.dataset.action = "copy";
      const edit = element("button", "card-button", "Edit");
      edit.type = "button";
      edit.dataset.action = "edit";
      actions.append(use, copy, edit);
    }
    footer.append(actions);
    card.append(footer);
    return card;
  }

  function currentSelectedCaption() {
    return state.captions.find((caption) => caption.id === state.selectedId) || null;
  }

  function captionById(id) {
    return state.captions.find((caption) => caption.id === id) || null;
  }

  function composeFullText(body, tags, platform) {
    const clean = String(body || "").trim();
    const tagText = (Array.isArray(tags) ? tags : []).filter(Boolean).join(" ").trim();
    if (!tagText) return clean;
    return `${clean}${platform === "x" ? " " : "\n\n"}${tagText}`;
  }

  function updateSelectionUI() {
    const selected = currentSelectedCaption();
    const limit = platformLimit(state.captionSet?.platform || state.platform);

    if (selected) {
      const editor = state.editingId === selected.id ? dom.captionGrid.querySelector(".card-editor") : null;
      const body = editor ? editor.value : selected.body;
      const text = composeFullText(body, selected.hashtags, state.captionSet?.platform || state.platform);
      dom.selectionLabel.textContent = `${selected.label} selected`;
      dom.selectionCount.textContent = `${text.length.toLocaleString()} / ${limit.toLocaleString()} characters`;
      dom.selectionCount.classList.toggle("is-over", text.length > limit);
    } else {
      dom.selectionLabel.textContent = "Select a direction";
      dom.selectionCount.textContent = "—";
      dom.selectionCount.classList.remove("is-over");
    }

    dom.copySelected.disabled = !selected;
    dom.exportCaptions.disabled = !state.captions.length;

    dom.captionGrid.querySelectorAll(".caption-card").forEach((card) => {
      const isSelected = card.dataset.id === state.selectedId;
      card.classList.toggle("is-selected", isSelected);
      const use = card.querySelector('[data-action="use"]');
      if (use) {
        use.textContent = isSelected ? "Selected" : "Use";
        use.setAttribute("aria-pressed", String(isSelected));
      }
    });
  }

  function selectCaption(id) {
    if (!captionById(id)) return;
    if (state.selectedId === id) {
      updateSelectionUI();
      return;
    }
    state.selectedId = id;
    updateSelectionUI();
  }

  function beginEdit(id) {
    const caption = captionById(id);
    if (!caption) return;
    state.selectedId = id;
    state.editingId = id;
    renderCaptions(state.captionSet);
    requestAnimationFrame(() => {
      const editor = dom.captionGrid.querySelector(".card-editor");
      if (!editor) return;
      editor.focus({ preventScroll: true });
      const end = editor.value.length;
      editor.setSelectionRange(end, end);
    });
  }

  function saveEdit() {
    const caption = captionById(state.editingId);
    if (!caption) return;
    const editor = dom.captionGrid.querySelector(".card-editor");
    const body = editor ? editor.value.replace(/\r\n/g, "\n").trim() : "";
    if (!body) {
      showToast("Add a line before saving this caption.");
      editor?.focus({ preventScroll: true });
      return;
    }
    caption.body = body;
    caption.text = composeFullText(body, caption.hashtags, state.captionSet?.platform || state.platform);
    caption.char_count = caption.text.length;
    state.editingId = null;
    renderCaptions(state.captionSet);
    requestAnimationFrame(() => {
      dom.captionGrid.querySelector('.caption-card.is-selected [data-action="edit"]')?.focus({ preventScroll: true });
    });
    showToast("Caption updated.");
  }

  function cancelEdit() {
    if (!state.editingId) return;
    const id = state.editingId;
    state.editingId = null;
    renderCaptions(state.captionSet);
    requestAnimationFrame(() => {
      const card = [...dom.captionGrid.querySelectorAll(".caption-card")]
        .find((node) => node.dataset.id === id);
      card?.querySelector('[data-action="edit"]')?.focus({ preventScroll: true });
    });
  }

  function refreshEditorCount(editor) {
    if (!editor) return;
    const card = editor.closest(".caption-card");
    const caption = card ? captionById(card.dataset.id) : null;
    if (!card || !caption) return;
    const limit = platformLimit(state.captionSet?.platform || state.platform);
    const text = composeFullText(editor.value, caption.hashtags, state.captionSet?.platform || state.platform);
    const count = card.querySelector(".char-count");
    if (count) {
      count.textContent = `${text.length.toLocaleString()} chars`;
      count.classList.toggle("is-over", text.length > limit);
    }
    if (state.selectedId === caption.id) {
      dom.selectionCount.textContent = `${text.length.toLocaleString()} / ${limit.toLocaleString()} characters`;
      dom.selectionCount.classList.toggle("is-over", text.length > limit);
    }
  }

  function copyCaption(id) {
    const caption = captionById(id);
    if (!caption) return;
    const editor = state.editingId === id ? dom.captionGrid.querySelector(".card-editor") : null;
    const body = editor ? editor.value : caption.body;
    const text = composeFullText(body, caption.hashtags, state.captionSet?.platform || state.platform);
    if (!text.trim()) {
      showToast("This caption is empty.");
      return;
    }
    copyText(text).then((copied) => {
      showToast(copied
        ? `${caption.label || "Caption"} copied — ready to paste.`
        : "The browser blocked the clipboard. Select the text and copy it manually.");
    });
  }

  function copySelectedCaption() {
    const caption = currentSelectedCaption();
    if (!caption) {
      showToast("Select a caption direction first.");
      return;
    }
    copyCaption(caption.id);
  }

  function exportAllCaptions() {
    if (!state.captions.length) {
      showToast("There are no captions to export yet.");
      return;
    }
    const captionSet = state.captionSet || {};
    const video = state.result?.analysis?.video || {};
    const tone = captionSet.tone_label || toneLabel(captionSet.tone);
    const platform = captionSet.platform_label || platformLabel(captionSet.platform);
    const lines = [
      `SceneScribe captions — ${platform} / ${tone}`,
      video.display_name ? `Source: ${video.display_name}` : "",
      "",
      ...state.captions.flatMap((caption, index) => [
        `${String(index + 1).padStart(2, "0")} · ${caption.label || "Caption"}${caption.recommended ? " (recommended)" : ""}`,
        caption.text || composeFullText(caption.body, caption.hashtags, captionSet.platform),
        ""
      ])
    ].filter((line) => line !== undefined);

    const blob = new Blob([`${lines.join("\n").trim()}\n`], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${slugify(video.display_name || "scenescribe")}-captions.txt`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    showToast("All six directions exported as a text file.");
  }

  async function shareResult() {
    if (!state.jobId) {
      showToast("This read has no saved link yet.");
      return;
    }
    updateUrlForJob(state.jobId, { push: false });
    const copied = await copyText(window.location.href);
    showToast(copied
      ? "Result link copied. It reopens this saved read."
      : "The browser blocked the clipboard. Copy the address bar link instead.");
  }

  /* ── Remix ──────────────────────────────────────────────── */

  async function runRemix({ announce = false } = {}) {
    if (!state.jobId || !state.captionSet) return;
    if (state.mode !== "studio") return;

    const requestedTone = dom.toneSelect.value || "auto";
    const requestedPlatform = dom.platformSelect.value || "instagram";
    state.tone = requestedTone;
    state.platform = requestedPlatform;
    state.remixToken += 1;
    const token = state.remixToken;
    const seed = ((Number(state.seed) || 0) + 1) % 100000;
    state.editingId = null;

    const buttonText = dom.remixButton.querySelector("span");
    dom.remixButton.classList.add("is-loading");
    dom.remixButton.disabled = true;
    dom.remixButton.setAttribute("aria-busy", "true");
    dom.toneSelect.disabled = true;
    dom.platformSelect.disabled = true;
    dom.captionGrid.classList.add("is-loading");
    dom.captionGrid.setAttribute("aria-busy", "true");
    if (buttonText) buttonText.textContent = "Reading…";

    try {
      const response = await fetch(`/api/jobs/${state.jobId}/remix`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          tone: requestedTone,
          platform: requestedPlatform,
          seed
        })
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.error || `The remix returned ${response.status}.`);
      }
      if (token !== state.remixToken) return;
      if (!payload?.caption_set) throw new Error("The remix came back without captions.");

      state.seed = Number(payload.caption_set.seed) || seed;
      renderCaptions(payload.caption_set);
      if (announce) showToast("Remixed — new phrasing, same read.");
    } catch (error) {
      if (token !== state.remixToken) return;
      syncSelectsFromCaptionSet(state.captionSet);
      showToast(error.message || "The remix didn’t come through. Try once more.");
    } finally {
      if (token === state.remixToken) {
        dom.remixButton.classList.remove("is-loading");
        dom.remixButton.disabled = false;
        dom.remixButton.removeAttribute("aria-busy");
        dom.toneSelect.disabled = false;
        dom.platformSelect.disabled = false;
        dom.captionGrid.classList.remove("is-loading");
        dom.captionGrid.removeAttribute("aria-busy");
        if (buttonText) buttonText.textContent = "Remix";
      }
    }
  }

  /* ── ClipForge workflow ─────────────────────────────────── */

  function clearForgeError() {
    dom.forgeError.textContent = "";
    dom.forgeError.hidden = true;
  }

  function showForgeError(message) {
    dom.forgeError.textContent = message;
    dom.forgeError.hidden = false;
  }

  function updateForgeSubmitState() {
    if (!dom.forgeSubmit) return;
    const unavailable = state.health?.clipforge?.available === false;
    dom.forgeSubmit.disabled = state.forgeSubmitting || unavailable;
    dom.forgeSubmit.classList.toggle("is-loading", state.forgeSubmitting);
    if (state.forgeSubmitting) {
      dom.forgeSubmit.setAttribute("aria-busy", "true");
      dom.forgeSubmitLabel.textContent = "Starting ClipForge…";
    } else {
      dom.forgeSubmit.removeAttribute("aria-busy");
      dom.forgeSubmitLabel.textContent = "Forge clips";
    }
  }

  function readForgePayload() {
    const source = dom.forgeSource.value.trim();
    if (!source) {
      throw new Error("Paste a YouTube or Twitch link, or a local video path.");
    }
    return {
      source,
      count: Number(dom.forgeCount.value) || 3,
      duration: Number(dom.forgeLength.value) || 30,
      aspect: dom.forgeAspect.value || "9:16",
      reframe: dom.forgeReframe.value || "blur",
      mode: dom.forgeMode.value || "auto",
      captions: Boolean(dom.forgeCaptions.checked),
      hook: dom.forgeHook.value.trim()
    };
  }

  function payloadFromRun(run) {
    const settings = run?.settings || {};
    return {
      source: String(run?.source || ""),
      count: Number(settings.count) || 3,
      duration: Number(settings.duration) || 30,
      aspect: String(settings.aspect || "9:16"),
      reframe: String(settings.reframe || "blur"),
      mode: String(settings.mode || "auto"),
      captions: Boolean(settings.captions),
      hook: String(settings.hook || "")
    };
  }

  function populateForgeFormFromRun(run) {
    if (!run) return;
    if (dom.forgeSource) dom.forgeSource.value = String(run.source || "");
    const settings = run.settings || {};
    const setSelect = (node, value) => {
      if (!node) return;
      const desired = String(value ?? "");
      if ([...node.options].some((option) => option.value === desired)) {
        node.value = desired;
      }
    };
    setSelect(dom.forgeCount, settings.count || 3);
    setSelect(dom.forgeLength, settings.duration || 30);
    setSelect(dom.forgeAspect, settings.aspect || "9:16");
    setSelect(dom.forgeReframe, settings.reframe || "blur");
    setSelect(dom.forgeMode, settings.mode || "auto");
    if (dom.forgeCaptions) dom.forgeCaptions.checked = Boolean(settings.captions);
    if (dom.forgeHook) dom.forgeHook.value = String(settings.hook || "");
  }

  function showForgeForm({ focus = false } = {}) {
    stopClipPolling();
    stopForgeElapsed();
    state.clipRunId = null;
    state.clipRun = null;
    state.lastForgeStage = "source";
    state.forgeRetryHandler = null;
    state.forgePollFailures = 0;
    clearForgeError();
    dom.forgeView.classList.remove("is-running", "is-results");
    dom.forgeWorkspace.hidden = false;
    dom.forgeProgress.hidden = true;
    dom.forgeResults.hidden = true;
    dom.forgeRunError.hidden = true;
    dom.forgeCancel.hidden = false;
    dom.forgeCancel.disabled = false;
    dom.forgeCancel.textContent = "Stop this run";
    dom.forgeLog.textContent = "Waiting for ClipForge…";
    dom.forgePercent.textContent = "0%";
    dom.forgeProgressFill.style.width = "0%";
    dom.forgeProgressBar.setAttribute("aria-valuenow", "0");
    document.title = FORGE_TITLE;
    updateForgeSubmitState();
    if (focus) {
      requestAnimationFrame(() => dom.forgeSource.focus({ preventScroll: true }));
    }
  }

  function openForgeLanding({ push = true, focus = true } = {}) {
    showForgeForm({ focus: false });
    setView("forge", { focus: false });
    updateUrlForForge({ push });
    if (focus) {
      requestAnimationFrame(() => dom.forgeSource.focus({ preventScroll: true }));
    }
  }

  async function startClipRun(event) {
    event.preventDefault();
    if (state.forgeSubmitting) return;
    let payload;
    try {
      payload = readForgePayload();
    } catch (error) {
      showForgeError(error.message || "Check the source and options.");
      return;
    }
    await submitClipRun(payload);
  }

  async function submitClipRun(payload, { retry = false } = {}) {
    if (state.forgeSubmitting) return;
    state.forgeSubmitting = true;
    state.forgePayload = { ...payload };
    clearForgeError();
    if (retry) {
      dom.forgeRunError.hidden = true;
      dom.forgeProgressMessage.textContent = "Starting another clip run";
    }
    updateForgeSubmitState();

    try {
      const response = await fetch("/api/clip-runs", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      const run = await readResponse(response);
      if (!run?.id || !CLIP_RUN_ID_RE.test(run.id)) {
        throw new Error("ClipForge did not return a valid clip run.");
      }
      state.clipRunId = run.id;
      state.clipRun = run;
      state.lastForgeStage = FORGE_STAGE_ORDER.includes(run.stage) ? run.stage : "source";
      updateUrlForClipRun(run.id, { push: true });
      showForgeProgress(run, { resetElapsed: true });
      startClipPolling();
    } catch (error) {
      if (retry && state.mode === "forge") {
        renderForgeConnectionError(error.message || "ClipForge could not start another run.");
      } else {
        showForgeError(error.message || "ClipForge could not start this run.");
      }
    } finally {
      state.forgeSubmitting = false;
      updateForgeSubmitState();
    }
  }

  function showForgeProgress(run, { resetElapsed = false } = {}) {
    state.clipRun = run;
    dom.forgeView.classList.add("is-running");
    dom.forgeView.classList.remove("is-results");
    dom.forgeWorkspace.hidden = true;
    dom.forgeResults.hidden = true;
    dom.forgeProgress.hidden = false;
    dom.forgeRunError.hidden = true;
    if (FORGE_STAGE_ORDER.includes(run.stage)) state.lastForgeStage = run.stage;
    updateForgeProgressUI(run);
    if (resetElapsed) {
      const created = Date.parse(run.created_at || "");
      startForgeElapsed(Number.isFinite(created) ? created : Date.now());
    }
    document.title = "Making clips — SceneScribe Studio";
  }

  function updateForgeProgressUI(run) {
    const percent = Math.max(0, Math.min(100, Math.round(Number(run.progress) || 0)));
    dom.forgePercent.textContent = `${percent}%`;
    dom.forgeProgressFill.style.width = `${percent}%`;
    dom.forgeProgressBar.setAttribute("aria-valuenow", String(percent));
    if (run.message) dom.forgeProgressMessage.textContent = run.message;
    setForgeLog(run.log);
    updateForgeStages(run);
    const terminal = run.status === "complete" || run.status === "error" || run.status === "cancelled";
    dom.forgeCancel.hidden = terminal;
    const stopping = /stopping/i.test(String(run.message || ""));
    dom.forgeCancel.disabled = stopping || state.forgeSubmitting;
    dom.forgeCancel.textContent = stopping ? "Stopping…" : "Stop this run";
  }

  function updateForgeStages(run) {
    const terminalFailure = run.status === "error" || run.status === "cancelled";
    const complete = run.status === "complete";
    let currentIndex = FORGE_STAGE_ORDER.indexOf(state.lastForgeStage);
    if (currentIndex < 0) currentIndex = 0;
    if (run.stage === "package") currentIndex = 3;

    dom.forgeStageItems.forEach((item, index) => {
      const key = item.dataset.forgeStage;
      const isError = terminalFailure && index === currentIndex;
      const isDone = complete || (!terminalFailure && index < currentIndex);
      const isActive = !complete && !terminalFailure && index === currentIndex;
      item.classList.toggle("is-done", isDone);
      item.classList.toggle("is-active", isActive);
      item.classList.toggle("is-error", isError);
      const status = item.querySelector(".stage-state");
      if (!status) return;
      if (complete || isDone) {
        status.textContent = "Done";
      } else if (isError) {
        status.textContent = "Stopped";
      } else if (isActive) {
        status.textContent = FORGE_STAGE_STATES[key] || "Working";
      } else {
        status.textContent = "Waiting";
      }
    });
  }

  function setForgeLog(log) {
    const text = String(log || "").trim() || "Waiting for ClipForge…";
    if (dom.forgeLog.textContent === text) return;
    const nearBottom = dom.forgeLog.scrollTop + dom.forgeLog.clientHeight
      >= dom.forgeLog.scrollHeight - 48;
    dom.forgeLog.textContent = text;
    if (nearBottom) dom.forgeLog.scrollTop = dom.forgeLog.scrollHeight;
  }

  function startForgeElapsed(startMs) {
    stopForgeElapsed();
    const numeric = Number(startMs);
    state.clipRunStarted = Number.isFinite(numeric) && numeric > 0
      ? Math.min(numeric, Date.now())
      : Date.now();
    const update = () => {
      dom.forgeElapsed.textContent = formatElapsed(state.clipRunStarted);
    };
    update();
    state.clipElapsedTimer = window.setInterval(update, 1000);
  }

  function stopForgeElapsed() {
    if (!state.clipElapsedTimer) return;
    window.clearInterval(state.clipElapsedTimer);
    state.clipElapsedTimer = null;
  }

  function startClipPolling() {
    stopClipPolling();
    state.clipPollFailures = 0;
    scheduleClipPoll(800);
  }

  function scheduleClipPoll(delay) {
    stopClipPolling();
    state.clipPollTimer = window.setTimeout(pollClipRun, delay);
  }

  function stopClipPolling() {
    if (!state.clipPollTimer) return;
    window.clearTimeout(state.clipPollTimer);
    state.clipPollTimer = null;
  }

  async function pollClipRun() {
    state.clipPollTimer = null;
    if (state.mode !== "forge" || !state.clipRunId) return;
    const runId = state.clipRunId;

    try {
      const response = await fetch(`/api/clip-runs/${runId}`, {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error(payload?.error || `The local studio returned ${response.status}.`);
        error.status = response.status;
        throw error;
      }
      const run = await response.json();
      if (state.clipRunId !== runId || state.mode !== "forge") return;
      state.clipPollFailures = 0;
      applyClipRun(run, { resetElapsed: false });
      if (run.status === "queued" || run.status === "running") {
        scheduleClipPoll(1000);
      }
    } catch (error) {
      if (state.clipRunId !== runId || state.mode !== "forge") return;
      if (error.status === 404) {
        showToast("That clip run has expired or was moved.");
        openForgeLanding({ push: false });
        return;
      }
      state.clipPollFailures += 1;
      if (state.clipPollFailures >= 5) {
        renderForgeConnectionError(
          "Lost the connection to the local studio. The clip run may still be going — check again in a moment."
        );
        return;
      }
      scheduleClipPoll(1100 + state.clipPollFailures * 500);
    }
  }

  function applyClipRun(run, { resetElapsed = false } = {}) {
    if (!run) return;
    if (FORGE_STAGE_ORDER.includes(run.stage)) state.lastForgeStage = run.stage;
    state.clipRun = run;
    state.forgePayload = payloadFromRun(run);
    if (run.status === "complete") {
      renderForgeResults(run);
      return;
    }
    if (run.status === "error" || run.status === "cancelled") {
      renderForgeRunError(run);
      return;
    }
    showForgeProgress(run, { resetElapsed });
  }

  function renderForgeConnectionError(message) {
    stopClipPolling();
    stopForgeElapsed();
    dom.forgeView.classList.add("is-running");
    dom.forgeView.classList.remove("is-results");
    dom.forgeWorkspace.hidden = true;
    dom.forgeResults.hidden = true;
    dom.forgeProgress.hidden = false;
    dom.forgeRunError.hidden = false;
    dom.forgeRunErrorTitle.textContent = "Lost the connection.";
    dom.forgeRunErrorText.textContent = message;
    dom.forgeCancel.hidden = true;
    state.forgeRetryHandler = () => {
      if (state.clipRunId) openClipRun(state.clipRunId, { push: false });
    };
    document.title = "Clip run paused — SceneScribe Studio";
  }

  function renderForgeRunError(run) {
    stopClipPolling();
    stopForgeElapsed();
    state.clipRun = run;
    state.forgePayload = payloadFromRun(run);
    dom.forgeView.classList.add("is-running");
    dom.forgeView.classList.remove("is-results");
    dom.forgeWorkspace.hidden = true;
    dom.forgeResults.hidden = true;
    dom.forgeProgress.hidden = false;
    updateForgeProgressUI(run);
    dom.forgeRunError.hidden = false;
    const cancelled = run.status === "cancelled";
    dom.forgeRunErrorTitle.textContent = cancelled
      ? "The clip run was stopped."
      : "The clip run stopped short.";
    dom.forgeRunErrorText.textContent = cancelled
      ? "Nothing else was added to this run. Try the source again or change the setup."
      : run.error || "ClipForge could not finish this source.";
    dom.forgeCancel.hidden = true;
    state.forgeRetryHandler = () => submitClipRun(state.forgePayload, { retry: true });
    document.title = "Clip run stopped — SceneScribe Studio";
  }

  async function cancelForgeRun() {
    if (!state.clipRunId) return;
    if (state.clipRun?.status !== "queued" && state.clipRun?.status !== "running") return;
    dom.forgeCancel.disabled = true;
    dom.forgeCancel.textContent = "Stopping…";
    try {
      const response = await fetch(`/api/clip-runs/${state.clipRunId}/cancel`, {
        method: "POST",
        headers: { Accept: "application/json" }
      });
      const payload = await readResponse(response);
      if (payload?.run) applyClipRun(payload.run, { resetElapsed: false });
      startClipPolling();
    } catch (error) {
      dom.forgeCancel.disabled = false;
      dom.forgeCancel.textContent = "Stop this run";
      showToast(error.message || "ClipForge could not be stopped. It may have already finished.");
    }
  }

  function renderForgeResults(run) {
    stopClipPolling();
    stopForgeElapsed();
    state.clipRun = run;
    state.clipRunId = run.id || state.clipRunId;
    state.forgePayload = payloadFromRun(run);
    dom.forgeView.classList.add("is-results");
    dom.forgeView.classList.remove("is-running");
    dom.forgeWorkspace.hidden = true;
    dom.forgeProgress.hidden = true;
    dom.forgeRunError.hidden = true;
    dom.forgeResults.hidden = false;

    const clips = Array.isArray(run.clips) ? run.clips : [];
    const count = clips.length;
    dom.forgeResultsTitle.textContent = count
      ? `${count} clip${count === 1 ? "" : "s"}, ready for their words.`
      : "No clips were written.";
    dom.forgeResultsMeta.textContent = forgeResultsMeta(run);

    dom.clipDeckGrid.replaceChildren(...clips.map((clip) => createClipCard(run, clip)));
    dom.forgeOpenFolder.disabled = false;
    const sourceTitle = run.source_info?.title || "ClipForge clips";
    document.title = `${sourceTitle} — clip deck — SceneScribe`;
  }

  function forgeResultsMeta(run) {
    const source = run.source_info || {};
    const bits = [];
    if (source.title) bits.push(String(source.title));
    if (source.channel && source.channel !== "ClipForge") bits.push(String(source.channel));
    if (source.duration_label) bits.push(String(source.duration_label));
    if (run.settings?.aspect) bits.push(String(run.settings.aspect));
    return bits.join("  ·  ");
  }

  function createClipCard(run, clip) {
    const index = Number(clip.index) || 0;
    const card = element("article", "clip-card");
    card.dataset.index = String(index);

    const poster = document.createElement("a");
    poster.className = "clip-poster";
    poster.href = clip.video_url || "#";
    poster.target = "_blank";
    poster.rel = "noopener";
    poster.setAttribute("aria-label", `Preview ${clip.label || `clip ${index}`} in a new tab`);
    if (clip.thumbnail_url) {
      const image = document.createElement("img");
      image.src = clip.thumbnail_url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      poster.append(image);
    } else {
      poster.innerHTML = FILM_ICON;
    }
    const posterTop = element("span", "clip-poster-top");
    posterTop.append(
      element("span", "clip-rank", clip.label || `Clip ${String(index).padStart(2, "0")}`),
      element("span", "clip-length", clip.duration_label || "")
    );
    const hint = element("span", "clip-preview-hint");
    hint.innerHTML = '<svg viewBox="0 0 18 18" aria-hidden="true"><path d="m7 5.5 5 3.5-5 3.5v-7Z" fill="currentColor"/></svg> Preview';
    poster.append(posterTop, hint);

    const body = element("div", "clip-card-body");
    const kicker = element("div", "clip-card-kicker");
    kicker.append(element("span", null, "ClipForge"));
    if (clip.caption_job_id) kicker.append(element("span", "clip-captioned", "Read"));
    body.append(kicker);

    body.append(element("h3", null, clip.label || `Clip ${String(index).padStart(2, "0")}`));
    const time = [clip.start_label, clip.end_label].filter(Boolean).join("  →  ");
    if (time) body.append(element("p", "clip-card-time", time));
    if (clip.reason) body.append(element("p", "clip-card-reason", clip.reason));

    const tags = element("div", "clip-card-tags");
    if (clip.aspect) tags.append(element("span", null, clip.aspect));
    if (clip.reframe) tags.append(element("span", null, clip.reframe));
    if (tags.childElementCount) body.append(tags);

    const actions = element("div", "clip-card-actions");
    const captionButton = element(
      "button",
      "button button--ink button--sm clip-caption-button",
      clip.caption_job_id ? "Open caption studio" : "Write captions"
    );
    captionButton.type = "button";
    captionButton.dataset.action = "caption";
    captionButton.dataset.index = String(index);
    const download = element("a", "button button--ghost button--sm", "Download");
    download.href = clip.download_url || clip.video_url || "#";
    download.download = "";
    actions.append(captionButton, download);
    body.append(actions);
    card.append(poster, body);
    return card;
  }

  async function openClipCaption(runId, index, button) {
    if (state.forgeCaptionBusy) return;
    state.forgeCaptionBusy = true;
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = "Opening…";
    try {
      const response = await fetch(`/api/clip-runs/${runId}/clips/${index}/caption`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ tone: "auto", platform: "instagram" })
      });
      const job = await readResponse(response);
      if (!job?.id) throw new Error("The studio did not return a caption job.");
      state.clipRunId = runId;
      updateUrlForJob(job.id, { push: true });
      await openJob(job.id);
    } catch (error) {
      showToast(error.message || "That clip could not be opened for captions.");
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = originalLabel;
      }
    } finally {
      state.forgeCaptionBusy = false;
    }
  }

  async function openClipRun(runId, { fromLink = false, push = false } = {}) {
    if (!CLIP_RUN_ID_RE.test(runId || "")) {
      history.replaceState({}, "", "/?forge=1");
      openForgeLanding({ push: false, focus: false });
      showToast("That clip deck link doesn’t look right.");
      return;
    }

    stopPolling();
    stopElapsed();
    stopClipPolling();
    stopForgeElapsed();
    state.clipRunId = runId;
    state.clipRun = null;
    state.clipPollFailures = 0;
    updateUrlForClipRun(runId, { push });
    setView("forge", { focus: false });

    dom.forgeView.classList.add("is-running");
    dom.forgeView.classList.remove("is-results");
    dom.forgeWorkspace.hidden = true;
    dom.forgeResults.hidden = true;
    dom.forgeProgress.hidden = false;
    dom.forgeRunError.hidden = true;
    dom.forgeCancel.hidden = true;
    dom.forgeProgressMessage.textContent = "Opening the saved clip deck";
    dom.forgeLog.textContent = "Reading the ClipForge run from this device…";
    dom.forgePercent.textContent = "0%";
    dom.forgeProgressFill.style.width = "0%";
    dom.forgeProgressBar.setAttribute("aria-valuenow", "0");
    document.title = "Loading the clip deck — SceneScribe Studio";

    try {
      const response = await fetch(`/api/clip-runs/${runId}`, {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error(payload?.error || `The local studio returned ${response.status}.`);
        error.status = response.status;
        throw error;
      }
      const run = await response.json();
      if (state.clipRunId !== runId || state.mode !== "forge") return;
      populateForgeFormFromRun(run);
      state.forgePayload = payloadFromRun(run);
      applyClipRun(run, { resetElapsed: true });
      if (run.status === "queued" || run.status === "running") {
        startClipPolling();
      }
    } catch (error) {
      if (state.clipRunId !== runId || state.mode !== "forge") return;
      if (error.status === 404) {
        state.clipRunId = null;
        showToast(fromLink
          ? "That clip deck has expired or was never saved."
          : "That clip deck could not be found.");
        openForgeLanding({ push: false });
        return;
      }
      renderForgeConnectionError(
        "The clip deck could not be opened. Make sure the local studio is still running, then try again."
      );
      state.forgeRetryHandler = () => openClipRun(runId, { push: false });
    }
  }

  async function openForgeOutputFolder() {
    if (!state.clipRunId) return;
    dom.forgeOpenFolder.disabled = true;
    try {
      const response = await fetch(`/api/clip-runs/${state.clipRunId}/open-folder`, {
        method: "POST",
        headers: { Accept: "application/json" }
      });
      await readResponse(response);
      showToast("Opened the ClipForge output folder.");
    } catch (error) {
      showToast(error.message || "The output folder could not be opened.");
    } finally {
      dom.forgeOpenFolder.disabled = false;
    }
  }

  /* ── Events ─────────────────────────────────────────────── */

  function bindEvents() {
    dom.dropzone.addEventListener("click", (event) => {
      if (event.target.closest("#clearFile")) return;
      dom.fileInput.click();
    });

    dom.dropzone.addEventListener("keydown", (event) => {
      if (event.target !== dom.dropzone) return;
      if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
        event.preventDefault();
        dom.fileInput.click();
      }
    });

    dom.fileInput.addEventListener("change", () => {
      const file = dom.fileInput.files?.[0];
      if (file) selectFile(file);
    });

    dom.clearFile.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      clearSelectedFile({ focus: true });
    });

    let dragDepth = 0;
    dom.dropzone.addEventListener("dragenter", (event) => {
      event.preventDefault();
      dragDepth += 1;
      dom.dropzone.classList.add("is-dragging");
    });
    dom.dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      dom.dropzone.classList.add("is-dragging");
    });
    dom.dropzone.addEventListener("dragleave", () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) dom.dropzone.classList.remove("is-dragging");
    });
    dom.dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      dragDepth = 0;
      dom.dropzone.classList.remove("is-dragging");
      const file = event.dataTransfer?.files?.[0];
      if (file) selectFile(file);
    });

    window.addEventListener("dragover", (event) => event.preventDefault());
    window.addEventListener("drop", (event) => event.preventDefault());

    dom.readButton.addEventListener("click", startUpload);
    dom.processStartOver.addEventListener("click", () => resetToLanding({ focusUpload: true }));
    dom.errorReset.addEventListener("click", () => resetToLanding({ focusUpload: true }));
    dom.errorRetry.addEventListener("click", () => {
      const retry = state.errorRetryHandler;
      if (retry) retry();
    });

    dom.newVideoLinks.forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        resetToLanding({ focusUpload: true });
      });
    });

    dom.homeLink.addEventListener("click", (event) => {
      event.preventDefault();
      if (state.mode === "landing") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        resetToLanding({ focusUpload: false });
      }
    });

    dom.shareButton.addEventListener("click", shareResult);
    dom.remixButton.addEventListener("click", () => runRemix({ announce: true }));
    dom.toneSelect.addEventListener("change", () => runRemix());
    dom.platformSelect.addEventListener("change", () => runRemix());
    dom.copySelected.addEventListener("click", copySelectedCaption);
    dom.exportCaptions.addEventListener("click", exportAllCaptions);

    dom.forgeOpeners.forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        openForgeLanding({ push: true });
      });
    });

    dom.forgeForm.addEventListener("submit", startClipRun);
    dom.forgeSource.addEventListener("input", () => {
      if (!dom.forgeError.hidden) clearForgeError();
    });
    dom.forgeCancel.addEventListener("click", cancelForgeRun);
    dom.forgeRetry.addEventListener("click", () => {
      const retry = state.forgeRetryHandler;
      if (retry) retry();
    });
    dom.forgeBackToForm.addEventListener("click", () => {
      showForgeForm({ focus: true });
      updateUrlForForge({ push: true });
    });
    dom.forgeAgain.addEventListener("click", () => {
      showForgeForm({ focus: true });
      updateUrlForForge({ push: true });
    });
    dom.forgeOpenFolder.addEventListener("click", openForgeOutputFolder);
    dom.forgeHomeLink.addEventListener("click", (event) => {
      event.preventDefault();
      resetToLanding({ focusUpload: false });
    });

    dom.clipDeckGrid.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) return;
      const button = event.target.closest("[data-action='caption']");
      if (!button || !state.clipRunId) return;
      event.preventDefault();
      openClipCaption(
        state.clipRunId,
        Number(button.dataset.index) || 0,
        button
      );
    });

    dom.studioDeckLink.addEventListener("click", (event) => {
      event.preventDefault();
      const runId = state.clipRunId;
      if (!runId || !CLIP_RUN_ID_RE.test(runId)) return;
      stopPolling();
      stopElapsed();
      state.jobId = null;
      state.job = null;
      state.result = null;
      state.captionSet = null;
      state.captions = [];
      state.selectedId = null;
      state.editingId = null;
      try {
        dom.videoPlayer.pause();
        dom.videoPlayer.removeAttribute("src");
        dom.videoPlayer.load();
      } catch {
        // The player may not have been initialised yet.
      }
      openClipRun(runId, { push: true });
    });

    dom.captionGrid.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) return;
      const card = event.target.closest(".caption-card");
      if (!card) return;
      const id = card.dataset.id;
      const action = event.target.closest("[data-action]")?.dataset.action;
      if (action === "use") {
        selectCaption(id);
        return;
      }
      if (action === "copy") {
        copyCaption(id);
        return;
      }
      if (action === "edit") {
        beginEdit(id);
        return;
      }
      if (action === "save") {
        saveEdit();
        return;
      }
      if (action === "cancel") {
        cancelEdit();
        return;
      }
      if (event.target.closest(".card-editor, button, textarea")) return;
      const selection = window.getSelection?.();
      if (selection && String(selection).length > 0) return;
      selectCaption(id);
    });

    dom.captionGrid.addEventListener("input", (event) => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.classList.contains("card-editor")) return;
      refreshEditorCount(event.target);
    });

    dom.videoPlayer.addEventListener("timeupdate", syncFrameHighlight);
    dom.videoPlayer.addEventListener("seeked", syncFrameHighlight);
    dom.videoPlayer.addEventListener("error", () => {
      if (!dom.videoPlayer.getAttribute("src")) return;
      if (dom.videoPlayer.dataset.errorShown === "true") return;
      dom.videoPlayer.dataset.errorShown = "true";
      showToast("This browser couldn’t preview the video. The download link still works.");
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (state.editingId) {
        event.preventDefault();
        cancelEdit();
      }
    });

    window.addEventListener("popstate", () => {
      const id = jobIdFromUrl();
      const runId = clipRunIdFromUrl();
      const forge = forgeRequestedFromUrl();

      if (id) {
        if (runId && CLIP_RUN_ID_RE.test(runId)) {
          state.clipRunId = runId;
        }
        if (!JOB_ID_RE.test(id)) {
          history.replaceState({}, "", "/");
          setView("landing", { focus: false });
          showToast("That result link doesn’t look right.");
          return;
        }
        if (state.mode === "studio" && state.jobId === id) return;
        openJob(id, { fromLink: true });
        return;
      }

      if (runId) {
        openClipRun(runId, { push: false, fromLink: true });
        return;
      }

      if (forge) {
        openForgeLanding({ push: false, focus: false });
        return;
      }

      if (state.mode !== "landing") {
        resetToLanding({ focusUpload: false, pushHistory: false });
      }
    });
  }

})();
