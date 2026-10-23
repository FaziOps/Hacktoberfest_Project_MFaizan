const $ = (id) => document.getElementById(id);
const MAX_SIDE = 1280;
const BUYER_LIMIT = 40;

const els = {
  video: $("video"), canvas: $("canvas"), viewport: $("viewport"), busy: $("busy"),
  capture: $("capture"), file: $("file"), rollId: $("roll-id"), widthCm: $("width-cm"),
  lengthM: $("length-m"), frameCm: $("frame-cm"), result: $("result"), latency: $("latency"),
  log: $("log"), report: $("report"),
};

let busy = false;

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

// "gemini:gemma-4-26b-a4b-it" -> { kind: "gemini", text: "Gemini API · gemma-4-26b-a4b-it" }
function source(model) {
  const [kind, ...rest] = (model || "").split(":");
  const name = rest.join(":");
  if (kind === "gemini") return { kind, text: `Gemini API · ${name}` };
  if (kind === "ollama") return { kind, text: `Offline · ${name}` };
  return { kind: "other", text: model || "" };
}

async function checkHealth() {
  const status = $("status");
  try {
    const h = await api("/api/health");
    // Auto mode running on the fallback only is usable but worth flagging.
    const degraded = h.ok && h.backend === "auto" && !h.backends[0].ok;
    status.className = `status ${!h.ok ? "err" : degraded ? "warn" : "ok"}`;
    status.title = (h.backends || [h]).map((b) => `${b.backend}: ${b.detail}`).join("\n");
    $("status-text").textContent = h.backend === "auto" ? h.detail : `${source(`${h.backend}:${h.model}`).text}`;
  } catch (err) {
    status.className = "status err";
    $("status-text").textContent = err.message;
  }
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1440 } },
      audio: false,
    });
    els.video.srcObject = stream;
  } catch {
    $("no-camera").hidden = false;
    els.capture.disabled = true;
  }
}

function frameToBlob() {
  const { videoWidth: w, videoHeight: h } = els.video;
  if (!w) return Promise.resolve(null);
  const scale = Math.min(1, MAX_SIDE / Math.max(w, h));
  els.canvas.width = Math.round(w * scale);
  els.canvas.height = Math.round(h * scale);
  els.canvas.getContext("2d").drawImage(els.video, 0, 0, els.canvas.width, els.canvas.height);
  return new Promise((resolve) => els.canvas.toBlob(resolve, "image/jpeg", 0.9));
}

function setBusy(on) {
  busy = on;
  els.busy.hidden = !on;
  els.capture.disabled = on || !els.video.srcObject;
}

async function inspect(blob, filename = "capture.jpg") {
  if (busy || !blob) return;
  if (!els.rollId.reportValidity()) return;
  setBusy(true);
  const form = new FormData();
  form.append("image", blob, filename);
  form.append("roll_id", els.rollId.value);
  form.append("width_cm", els.widthCm.value);
  form.append("length_m", els.lengthM.value);
  form.append("frame_cm", els.frameCm.value);
  try {
    const result = await api("/api/inspect", { method: "POST", body: form });
    renderResult(result, URL.createObjectURL(blob));
    await loadRoll();
    checkHealth();
  } catch (err) {
    els.result.className = "result";
    els.result.innerHTML = `<p class="warning">${escapeHtml(err.message)}</p>`;
  } finally {
    setBusy(false);
  }
}

const QUALITY_WARNINGS = {
  blurry: "Photo is blurry. Hold the camera steady and capture again.",
  too_dark: "Photo is too dark. Add light and capture again.",
  not_fabric: "This does not look like fabric.",
};

function renderResult(r, imageUrl) {
  const src = source(r.model);
  els.latency.innerHTML = `${(r.latency_ms / 1000).toFixed(1)} s <span class="badge ${src.kind}">${escapeHtml(src.text)}</span>`;
  const warning = QUALITY_WARNINGS[r.image_quality];
  const defects = r.defects.length
    ? `<ul class="defects">${r.defects.map((d) => `
        <li class="defect">
          <div class="defect-head">
            <span class="defect-name">${escapeHtml(d.name_en)}<span class="ur" lang="ur">${escapeHtml(d.name_ur)}</span></span>
            <span class="pts">+${d.points} pt${d.points > 1 ? "s" : ""}</span>
          </div>
          <p>${escapeHtml(d.description)}</p>
          <p>${escapeHtml(d.location)} · ${d.size.replace(/_/g, " ")} · ${Math.round(d.confidence * 100)}% sure</p>
        </li>`).join("")}</ul>`
    : `<p class="clean">No defects found ✓</p>`;
  els.result.className = "result";
  els.result.innerHTML = `
    <div class="result-top">
      <img src="${imageUrl}" alt="Inspected fabric">
      <div>
        <p>${escapeHtml(r.fabric) || "Fabric"}</p>
        ${warning ? `<p class="warning">${warning}</p>` : ""}
        ${r.fallback_reason ? `<p class="fallback">${escapeHtml(r.fallback_reason)}</p>` : ""}
        <p><strong>${r.points}</strong> penalty points in this photo</p>
      </div>
    </div>
    ${defects}`;
}

function renderRoll(roll) {
  const s = roll?.summary;
  const letter = $("grade-letter");
  letter.textContent = s ? s.grade : "–";
  letter.className = `grade-letter ${s ? s.grade : ""}`;
  $("grade-roll").textContent = els.rollId.value;
  $("score").textContent = s ? s.points_per_100_sq_yd : 0;
  $("total-points").textContent = s ? s.total_points : 0;
  $("defect-count").textContent = s ? s.defect_count : 0;
  $("photo-count").textContent = roll ? roll.inspections.length : 0;
  const pct = s ? Math.min(100, (s.points_per_100_sq_yd / (BUYER_LIMIT * 1.5)) * 100) : 0;
  $("meter-fill").style.width = `${pct}%`;

  els.log.innerHTML = (roll?.inspections ?? []).slice().reverse().map((i) => `
    <figure class="log-item" style="margin:0">
      <img src="${i.image_url}" alt="Photo ${i.id}" loading="lazy">
      <div><span>${i.defects.length} defect${i.defects.length === 1 ? "" : "s"}</span><strong>+${i.points}</strong></div>
    </figure>`).join("");
}

async function loadRoll() {
  try {
    renderRoll(await api(`/api/rolls/${encodeURIComponent(els.rollId.value)}`));
  } catch {
    renderRoll(null);
  }
}

async function writeReport() {
  const button = $("report-btn");
  button.disabled = true;
  button.textContent = "Gemma 4 is writing…";
  try {
    const r = await api(`/api/rolls/${encodeURIComponent(els.rollId.value)}/report`);
    $("report-ur").textContent = r.urdu;
    $("report-en").textContent = r.english;
    $("report-by").textContent = r.written_by === "template"
      ? "Written from the inspection log (model unavailable)"
      : `Written by Gemma 4 (${source(r.written_by).text}) from the inspection log`
        + (r.fallback_reason ? `. ${r.fallback_reason}` : "");
    els.report.hidden = false;
    $("print-btn").hidden = false;
  } catch (err) {
    alert(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Write report";
  }
}

els.capture.addEventListener("click", async () => inspect(await frameToBlob()));
els.file.addEventListener("change", () => {
  const file = els.file.files[0];
  if (file) inspect(file, file.name);
  els.file.value = "";
});
els.viewport.addEventListener("dragover", (e) => { e.preventDefault(); els.viewport.classList.add("drag"); });
els.viewport.addEventListener("dragleave", () => els.viewport.classList.remove("drag"));
els.viewport.addEventListener("drop", (e) => {
  e.preventDefault();
  els.viewport.classList.remove("drag");
  const file = e.dataTransfer.files[0];
  if (file) inspect(file, file.name);
});
document.addEventListener("keydown", async (e) => {
  if (e.code === "Space" && !["INPUT", "BUTTON"].includes(document.activeElement.tagName)) {
    e.preventDefault();
    inspect(await frameToBlob());
  }
});
els.rollId.addEventListener("change", () => { els.report.hidden = true; loadRoll(); });
$("reset").addEventListener("click", async () => {
  if (!confirm(`Delete all photos for roll ${els.rollId.value}?`)) return;
  await api(`/api/rolls/${encodeURIComponent(els.rollId.value)}`, { method: "DELETE" });
  els.result.className = "result empty";
  els.result.textContent = "Capture a photo to start inspecting.";
  els.latency.textContent = "";
  els.report.hidden = true;
  loadRoll();
});
$("report-btn").addEventListener("click", writeReport);
$("print-btn").addEventListener("click", () => window.print());
$("roll-form").addEventListener("submit", (e) => e.preventDefault());

checkHealth();
startCamera();
loadRoll();
