// Storage list + semantic search (top_k=null = trả tất cả CV đạt filter)
// Click 1 row gọi openCVModal(cv_key) ở modal.js

let _lastView = "list";       // "list" | "search"
let _lastQuery = "";

async function loadStorage() {
  _lastView = "list";
  const wrap = document.getElementById("storage-content");
  wrap.innerHTML = `<div class="empty-state">Đang tải...</div>`;
  clearAlert("storage-alert");
  try {
    const body = await fetchJSON(`${API}/Storage`);
    renderStorageList(body.cv_storage || {});
  } catch (e) {
    wrap.innerHTML = "";
    showAlert("storage-alert", `Lỗi: ${e.message}`, "error");
  }
}

function renderStorageList(cvs) {
  const entries = Object.entries(cvs);
  document.getElementById("storage-count").textContent = `${entries.length} CV`;
  const target = document.getElementById("storage-content");
  if (!entries.length) {
    target.innerHTML = `<div class="empty-state">Chưa có CV nào. Upload ở tab "Upload CV".</div>`;
    return;
  }
  target.innerHTML = entries.map(([key, cv]) => cvRowHtml(key, cv)).join("");
  attachCVRowClicks(target);
}

function cvRowHtml(key, cv) {
  const skills = (cv.skills || []).slice(0, 6).map(s => `<span class="skill-chip">${escapeHtml(s)}</span>`).join("");
  const more = (cv.skills || []).length > 6 ? `<span class="skill-chip">+${(cv.skills || []).length - 6}</span>` : "";
  const years = cv.years_exp !== null && cv.years_exp !== undefined ? `${cv.years_exp} năm KN` : "—";
  return `<div class="cv-row" data-key="${escapeHtml(key)}">
    <div class="cv-row-head">
      <div class="cv-row-name">${escapeHtml(cv.name || key)}</div>
      <div class="cv-row-file">${escapeHtml(cv.file_name || "")}</div>
    </div>
    <div class="cv-row-meta">
      <span>📧 ${escapeHtml(cv.email || "—")}</span>
      <span>📞 ${escapeHtml(cv.phone || "—")}</span>
      <span>🎯 ${escapeHtml(years)}</span>
    </div>
    <div style="margin-top:6px">${skills}${more}</div>
  </div>`;
}

function attachCVRowClicks(scope) {
  scope.querySelectorAll(".cv-row[data-key]").forEach(row => {
    row.addEventListener("click", () => {
      const key = row.dataset.key;
      if (key && typeof openCVModal === "function") openCVModal(key);
    });
  });
}

async function runSearchOrReset() {
  const input = document.getElementById("storage-search-input");
  const q = (input.value || "").trim();
  if (!q) { loadStorage(); return; }
  _lastView = "search";
  _lastQuery = q;
  clearAlert("storage-alert");
  setBusy("storage-search-input", "storage-spinner", false);
  document.getElementById("storage-spinner").classList.add("show");
  const wrap = document.getElementById("storage-content");
  wrap.innerHTML = `<div class="empty-state">Đang tìm...</div>`;
  try {
    const body = await fetchJSON(`${API}/Search/Semantic`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, top_k: null }),
    });
    renderSearchResults(body);
  } catch (e) {
    wrap.innerHTML = "";
    showAlert("storage-alert", `Lỗi: ${e.message}`, "error");
  } finally {
    document.getElementById("storage-spinner").classList.remove("show");
  }
}

function renderSearchResults(body) {
  const results = body.results || [];
  document.getElementById("storage-count").textContent = `${results.length} kết quả`;
  const target = document.getElementById("storage-content");
  if (!results.length) {
    target.innerHTML = `<div class="empty-state">Không tìm thấy CV phù hợp.</div>`;
    return;
  }
  target.innerHTML = results.map(r => {
    const cv = r.cv || {};
    const chunks = (r.matched_chunks || []).map(c => `<div class="match-chunk"><span class="section-tag">[${escapeHtml(c.section)}]</span>${escapeHtml(c.text)}<span class="score-tag">${(c.score || 0).toFixed(3)}</span></div>`).join("");
    return `<div class="cv-row" data-key="${escapeHtml(r.cv_key)}">
      <div class="cv-row-head">
        <div class="cv-row-name">${escapeHtml(cv.name || r.cv_key)}</div>
        <span class="badge">best ${(r.score || 0).toFixed(3)}</span>
      </div>
      <div class="cv-row-meta">
        <span>📧 ${escapeHtml(cv.email || "—")}</span>
        <span>🎯 ${cv.years_exp !== null && cv.years_exp !== undefined ? cv.years_exp + " năm KN" : "—"}</span>
      </div>
      <div style="margin-top:8px">${chunks}</div>
    </div>`;
  }).join("");
  attachCVRowClicks(target);
}

// Used by reloadCurrentView() in common.js
function reloadStorageView() {
  if (_lastView === "search" && _lastQuery) {
    document.getElementById("storage-search-input").value = _lastQuery;
    runSearchOrReset();
  } else {
    loadStorage();
  }
}

// Auto-load when this script runs (tab might already be active if user navigates to /#storage)
document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("panel-storage")) loadStorage();
});
