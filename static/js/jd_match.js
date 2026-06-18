// JD và CV matching, paste text hoặc upload file

function onJDFileSelected(input) {
  const f = input.files && input.files[0];
  const dz = document.getElementById("jd-dz-filename");
  if (f) dz.textContent = f.name; else dz.textContent = "";
}

async function runJDMatch() {
  clearAlert("jd-match-alert");
  const text = document.getElementById("jd-text").value.trim();
  const fileInput = document.getElementById("jd-file-input");
  const file = fileInput.files && fileInput.files[0];
  const top_k = parseInt(document.getElementById("jd-top-k").value, 10) || 5;
  const strict_skills = document.getElementById("jd-strict-skills").checked;
  const strict_years = document.getElementById("jd-strict-years").checked;
  const llm_evaluate = document.getElementById("jd-llm-evaluate").checked;

  if (!text && !file) {
    showAlert("jd-match-alert", "Paste JD hoặc upload file trước.", "error");
    return;
  }

  setBusy("jd-match-btn", "jd-match-spinner", true);
  document.getElementById("jd-match-results").innerHTML = "";

  try {
    let body;
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("top_k", String(top_k));
      fd.append("strict_skills_filter", String(strict_skills));
      fd.append("strict_years_filter", String(strict_years));
      fd.append("llm_evaluate", String(llm_evaluate));
      body = await fetchJSON(`${API}/Match/JD/Upload`, { method: "POST", body: fd });
    } else {
      body = await fetchJSON(`${API}/Match/JD`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: text, top_k, strict_skills_filter: strict_skills, strict_years_filter: strict_years, llm_evaluate }),
      });
    }
    renderJDMatchResults(body);
  } catch (e) {
    showAlert("jd-match-alert", `Lỗi: ${e.message}`, "error");
  } finally {
    setBusy("jd-match-btn", "jd-match-spinner", false);
  }
}

function renderJDMatchResults(body) {
  const target = document.getElementById("jd-match-results");
  const pj = body.parsed_jd || {};
  const skillsHtml = (pj.required_skills || []).map(s => `<span class="skill-chip">${escapeHtml(s)}</span>`).join(" ") || '<span style="color:var(--muted)">(không có)</span>';
  const yearsRange = `${pj.min_years_exp ?? "—"} … ${pj.max_years_exp ?? "—"}`;
  const summary = `<div class="jd-parsed-summary">
    <h4>JD đã phân tích</h4>
    <div style="margin-bottom:6px"><strong>Tóm tắt:</strong> ${escapeHtml(pj.summary || "(không có)")}</div>
    <div style="margin-bottom:6px"><strong>Năm KN:</strong> ${escapeHtml(yearsRange)}</div>
    <div><strong>Skills:</strong> ${skillsHtml}</div>
  </div>`;

  const results = body.results || [];
  if (!results.length) {
    target.innerHTML = summary + `<div class="empty-state">Không tìm thấy CV phù hợp.</div>`;
    return;
  }

  const rows = results.map((r, i) => {
    const cv = r.cv || {};
    const ev = r.llm_evaluation;
    const vecPct = Math.round((r.score || 0) * 100);
    // Có eval thì headline dùng điểm LLM (đã re-rank theo nó), vector hiện phụ ở meta
    const headPct = ev ? Math.round((ev.score || 0) * 100) : vecPct;
    const rm = ev ? recMeta(ev.recommendation) : null;
    const recBadge = rm ? `<span class="jd-rec-badge" style="background:${rm.color}">${escapeHtml(rm.label)}</span>` : "";
    const vecNote = ev ? `<span>📊 Vector ${vecPct}%</span>` : "";
    const chunks = (r.matched_chunks || []).map(c => `<div class="match-chunk"><span class="section-tag">[${escapeHtml(c.section)}]</span>${escapeHtml(c.text)}<span class="score-tag">${(c.score || 0).toFixed(3)}</span></div>`).join("");
    return `<div class="cv-row" data-key="${escapeHtml(r.cv_key)}">
      <div class="cv-row-head">
        <div class="cv-row-name"><span class="jd-rank-badge">#${i + 1}</span>${escapeHtml(cv.name || r.cv_key)}${recBadge}</div>
        <div class="score-pct">${headPct}%</div>
      </div>
      <div class="score-bar"><div style="width:${headPct}%"></div></div>
      <div class="cv-row-meta">
        <span>📧 ${escapeHtml(cv.email || "—")}</span>
        <span>🎯 ${cv.years_exp !== null && cv.years_exp !== undefined ? cv.years_exp + " năm KN" : "—"}</span>
        ${vecNote}
      </div>
      ${ev ? renderEvalBlock(ev) : ""}
      <details style="margin-top:8px"><summary style="cursor:pointer;color:var(--muted);font-size:12px">${(r.matched_chunks || []).length} chunks khớp</summary>${chunks}</details>
    </div>`;
  }).join("");

  target.innerHTML = summary + rows;
  // Click row mở modal (reuse from modal.js)
  target.querySelectorAll(".cv-row[data-key]").forEach(row => {
    row.addEventListener("click", e => {
      // Don't trigger when toggling <details>
      if (e.target.closest("details") || e.target.tagName === "SUMMARY") return;
      const key = row.dataset.key;
      if (key && typeof openCVModal === "function") openCVModal(key);
    });
  });
}

// Map nhãn recommendation từ LLM thành label tiếng Việt cộng màu
function recMeta(rec) {
  const map = {
    strong: { label: "Rất phù hợp", color: "var(--success)" },
    good: { label: "Phù hợp", color: "var(--accent)" },
    weak: { label: "Chưa phù hợp", color: "var(--warn)" },
    reject: { label: "Loại", color: "var(--danger)" },
  };
  return map[(rec || "").toLowerCase()] || { label: rec || "—", color: "var(--muted)" };
}

// Render khối đánh giá LLM cho 1 CV (reasoning, skill khớp/thiếu, điểm mạnh, lưu ý)
function renderEvalBlock(ev) {
  const rm = recMeta(ev.recommendation);
  const matched = (ev.matched_skills || []).map(s => `<span class="skill-chip">${escapeHtml(s)}</span>`).join(" ") || '<span style="color:var(--muted)">—</span>';
  const missing = (ev.missing_skills || []).map(s => `<span class="skill-chip" style="border-color:var(--danger);color:#ff9a9a">${escapeHtml(s)}</span>`).join(" ") || '<span style="color:var(--muted)">—</span>';
  const listOr = arr => (arr && arr.length) ? `<ul style="margin:4px 0 0;padding-left:18px">${arr.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : '<span style="color:var(--muted)">—</span>';
  return `<div class="llm-eval-block" style="margin-top:10px;padding:10px;background:var(--card-2);border-radius:6px;border-left:3px solid ${rm.color}">
    ${ev.reasoning ? `<div style="font-size:13px;line-height:1.5">${escapeHtml(ev.reasoning)}</div>` : ""}
    ${ev.experience_fit ? `<div style="margin-top:8px;font-size:12px"><strong>Kinh nghiệm:</strong> ${escapeHtml(ev.experience_fit)}</div>` : ""}
    <div style="margin-top:8px;font-size:12px"><strong>Skill khớp:</strong> ${matched}</div>
    <div style="margin-top:6px;font-size:12px"><strong>Skill thiếu:</strong> ${missing}</div>
    <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;font-size:12px">
      <div style="flex:1;min-width:160px"><strong>Điểm mạnh</strong>${listOr(ev.strengths)}</div>
      <div style="flex:1;min-width:160px"><strong>Lưu ý</strong>${listOr(ev.concerns)}</div>
    </div>
  </div>`;
}
