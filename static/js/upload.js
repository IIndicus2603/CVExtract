// Upload 1 CV + upload folder, render kết quả

function onFileSelected(input) {
  const f = input.files && input.files[0];
  const dz = document.getElementById("dz-filename");
  const btn = document.getElementById("upload-btn");
  if (f) {
    dz.textContent = f.name;
    if (btn) btn.disabled = false;
  } else {
    dz.textContent = "";
    if (btn) btn.disabled = true;
  }
}

async function uploadCV() {
  const input = document.getElementById("file-input");
  const f = input.files && input.files[0];
  if (!f) return;
  clearAlert("upload-alert");
  setBusy("upload-btn", "upload-spinner", true);
  try {
    const fd = new FormData();
    fd.append("file", f);
    const body = await fetchJSON(`${API}/UploadCV`, { method: "POST", body: fd });
    renderUploadResult(body.results);
    showAlert("upload-alert", `Upload thành công: ${body.results.file_name}`, "success");
  } catch (e) {
    showAlert("upload-alert", `Lỗi: ${e.message}`, "error");
  } finally {
    setBusy("upload-btn", "upload-spinner", false);
  }
}

function renderUploadResult(r) {
  const card = document.getElementById("upload-result");
  const name = document.getElementById("upload-result-name");
  const badge = document.getElementById("upload-result-badge");
  const body = document.getElementById("upload-result-body");
  card.style.display = "block";
  name.textContent = r.file_name;
  badge.textContent = r.status;
  badge.className = `badge ${r.status === "success" ? "success" : "error"}`;
  let pretty;
  try { pretty = JSON.stringify(JSON.parse(r.text), null, 2); }
  catch { pretty = r.text || ""; }
  body.innerHTML = `<pre style="white-space:pre-wrap;background:var(--bg);padding:12px;border-radius:6px;font-size:12px;margin:0;overflow:auto;max-height:480px">${escapeHtml(pretty)}</pre>`;
}

// Khi user chọn folder qua webkitdirectory, browser populate FileList với mọi file trong folder
// Filter client-side để chỉ upload .pdf/.docx, giảm payload và tránh trip backend với file rác
const _BATCH_SUPPORTED = /\.(pdf|docx)$/i;
let _batchFiles = [];

function onBatchFolderSelected(input) {
  const all = Array.from(input.files || []);
  _batchFiles = all.filter(f => _BATCH_SUPPORTED.test(f.name));
  const dz = document.getElementById("batch-folder-filename");
  const btn = document.getElementById("batch-btn");
  if (!all.length) {
    dz.textContent = "";
    btn.disabled = true;
    return;
  }
  const folderName = (all[0].webkitRelativePath || all[0].name).split("/")[0] || "(folder)";
  const skipped = all.length - _batchFiles.length;
  dz.textContent = `📁 ${folderName} — ${_batchFiles.length} file hợp lệ${skipped ? ` (bỏ qua ${skipped} file khác)` : ""}`;
  btn.disabled = _batchFiles.length === 0;
}

async function uploadBatch() {
  if (!_batchFiles.length) return;
  clearAlert("batch-alert");
  setBusy("batch-btn", "batch-spinner", true);
  document.getElementById("batch-results").innerHTML = "";
  try {
    const fd = new FormData();
    _batchFiles.forEach(f => fd.append("files", f, f.name));
    const body = await fetchJSON(`${API}/UploadMultipleCVs`, { method: "POST", body: fd });
    renderBatchResults(body);
    showAlert("batch-alert", `Xong: ${body.succeeded}/${body.total} thành công, ${body.failed} lỗi.`, body.failed ? "info" : "success");
  } catch (e) {
    showAlert("batch-alert", `Lỗi: ${e.message}`, "error");
  } finally {
    setBusy("batch-btn", "batch-spinner", false);
  }
}

function renderBatchResults(b) {
  const target = document.getElementById("batch-results");
  const tokenLine = b.tokens
    ? `<div style="font-size:12px;color:var(--muted);margin-bottom:8px">Tokens: prompt=${b.tokens.prompt}, completion=${b.tokens.completion}, total=${b.tokens.total}</div>`
    : "";
  const rows = (b.results || []).map(r => {
    const kind = r.status === "success" ? "success" : "error";
    const msg = r.error_message ? ` — ${escapeHtml(r.error_message)}` : "";
    return `<div class="cv-row"><div class="cv-row-head"><div class="cv-row-name">${escapeHtml(r.file_name)}</div><span class="badge ${kind}">${escapeHtml(r.status)}</span></div><div class="cv-row-meta">${msg}</div></div>`;
  }).join("");
  target.innerHTML = `<div class="card"><h2 class="card-title">Kết quả batch (${b.succeeded}/${b.total})</h2>${tokenLine}${rows || '<div class="empty-state">Không có file</div>'}</div>`;
}
