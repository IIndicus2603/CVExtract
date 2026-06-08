// Helpers + tab switching dùng chung cho mọi panel

const API = "";

// fetch JSON; throw Error(message) nếu HTTP !ok, message = detail nếu có
async function fetchJSON(url, opts) {
  const resp = await fetch(url, opts);
  let body = null;
  try { body = await resp.json(); } catch { /* may be empty */ }
  if (!resp.ok) {
    const msg = (body && (body.detail || body.message)) || resp.statusText || `HTTP ${resp.status}`;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
}

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function showAlert(elId, msg, kind) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = msg;
  el.className = `alert ${kind || "info"} show`;
}

function clearAlert(elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = "alert";
  el.textContent = "";
}

function setBusy(btnId, spinnerId, busy) {
  const btn = document.getElementById(btnId);
  const sp = spinnerId ? document.getElementById(spinnerId) : null;
  if (btn) btn.disabled = !!busy;
  if (sp) sp.classList.toggle("show", !!busy);
}

// Generic drop-zone wiring: clicking opens input, drag-and-drop sets file
function onDropZone(zoneId, inputId, onFile) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  if (!zone || !input) return;

  ["dragenter", "dragover"].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); zone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); zone.classList.remove("dragover");
  }));
  zone.addEventListener("drop", e => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) {
      // Set file on the hidden input so subsequent uploads can read it
      const dt = new DataTransfer();
      dt.items.add(f);
      input.files = dt.files;
      onFile && onFile(f);
    }
  });
}

// Tab switching, called from inline onclick="switchTab('storage')"
let _currentTab = "upload";
function switchTab(name) {
  _currentTab = name;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === `panel-${name}`));
  // Lazy load when entering Hồ sơ tab
  if (name === "storage" && typeof loadStorage === "function") loadStorage();
}

// Re-run the active tab's main loader (used by "Làm mới" button in Hồ sơ)
function reloadCurrentView() {
  if (_currentTab === "storage" && typeof reloadStorageView === "function") reloadStorageView();
}

// Boot: storage auto-loads when its tab first shown; upload is the default active panel
document.addEventListener("DOMContentLoaded", () => {
  // Wire drop zones if present
  if (document.getElementById("drop-zone") && typeof onFileSelected === "function") {
    onDropZone("drop-zone", "file-input", () => onFileSelected(document.getElementById("file-input")));
  }
  if (document.getElementById("jd-drop-zone") && typeof onJDFileSelected === "function") {
    onDropZone("jd-drop-zone", "jd-file-input", () => onJDFileSelected(document.getElementById("jd-file-input")));
  }
});
