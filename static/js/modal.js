// Modal chi tiết CV: view + edit + chat + delete confirm

let _modalCV = null;          // current loaded CV (parsed dict + meta)
let _modalKey = null;
let _modalMode = "view";      // "view" | "edit" | "chat"

// Toggle icon buttons trong header theo mode hiện tại
function setModalMode(mode) {
  _modalMode = mode;
  const isView = mode === "view";
  const isChat = mode === "chat";
  document.getElementById("cv-modal-chat-btn").style.display = isView ? "inline-flex" : "none";
  document.getElementById("cv-modal-edit-btn").style.display = isView ? "inline-flex" : "none";
  document.getElementById("cv-modal-delete-btn").style.display = isView ? "inline-flex" : "none";
  document.getElementById("cv-modal-back-btn").style.display = isChat ? "inline-flex" : "none";
  document.getElementById("cv-modal-reset-chat-btn").style.display = isChat ? "inline-flex" : "none";
}

async function openCVModal(cv_key) {
  _modalKey = cv_key;
  const back = document.getElementById("cv-modal-backdrop");
  const title = document.getElementById("cv-modal-title");
  const body = document.getElementById("cv-modal-body");
  const footer = document.getElementById("cv-modal-footer");
  title.textContent = "Đang tải...";
  body.innerHTML = `<div class="empty-state">Loading...</div>`;
  body.classList.remove("chat-mode");
  footer.style.display = "none";
  setModalMode("view");
  back.classList.add("show");
  try {
    const cv = await fetchJSON(`${API}/Storage/${encodeURIComponent(cv_key)}`);
    _modalCV = cv;
    renderCVView(cv);
  } catch (e) {
    body.innerHTML = `<div class="alert error show">Lỗi: ${escapeHtml(e.message)}</div>`;
  }
}

function closeCVModal(ev) {
  // Only close if the click is on the backdrop itself, or no event was given (icon-btn handler)
  if (ev && ev.target && ev.target.id !== "cv-modal-backdrop") return;
  document.getElementById("cv-modal-backdrop").classList.remove("show");
  document.getElementById("cv-modal-body").classList.remove("chat-mode");
  _modalCV = null; _modalKey = null; _modalMode = "view";
  if (typeof _resetActiveChatSession === "function") _resetActiveChatSession();
}

function renderCVView(cv) {
  const body = document.getElementById("cv-modal-body");
  const footer = document.getElementById("cv-modal-footer");
  setModalMode("view");
  document.getElementById("cv-modal-title").textContent = cv.name || _modalKey;
  body.classList.remove("chat-mode");
  footer.style.display = "none";
  body.innerHTML = `
    <div class="modal-section">
      <h4>Header</h4>
      <div class="field-row"><div class="field-label">Tên</div><div class="field-value">${escapeHtml(cv.name || "—")}</div></div>
      <div class="field-row"><div class="field-label">Email</div><div class="field-value">${escapeHtml(cv.email || "—")}</div></div>
      <div class="field-row"><div class="field-label">SĐT</div><div class="field-value">${escapeHtml(cv.phone || "—")}</div></div>
      <div class="field-row"><div class="field-label">Năm KN</div><div class="field-value">${cv.years_exp !== null && cv.years_exp !== undefined ? cv.years_exp : "—"}</div></div>
    </div>
    ${cv.summary ? `<div class="modal-section"><h4>Tóm tắt</h4><div>${escapeHtml(cv.summary)}</div></div>` : ""}
    ${listSection("Skills", (cv.skills || []).map(s => `<span class="skill-chip">${escapeHtml(s)}</span>`).join(" "))}
    ${entriesSection("Học vấn", cv.education, ["degree", "school", "duration"])}
    ${entriesSection("Kinh nghiệm", cv.work_history, ["role", "company", "duration", "description"])}
    ${entriesSection("Dự án", cv.projects, ["name", "description", "tech", "duration", "url"])}
    ${entriesSection("Giải thưởng", cv.awards, ["name", "issuer", "year", "description"])}
    ${entriesSection("Chứng chỉ", cv.certifications, ["name", "issuer", "year"])}
  `;
}

function listSection(title, html) {
  if (!html) return "";
  return `<div class="modal-section"><h4>${escapeHtml(title)}</h4><div>${html}</div></div>`;
}

function entriesSection(title, entries, fields) {
  if (!entries || !entries.length) return "";
  const rows = entries.map(e => {
    const lines = fields.map(f => {
      const v = e[f];
      if (v === null || v === undefined || v === "") return "";
      const val = Array.isArray(v) ? v.join(", ") : String(v);
      return `<div class="field-row"><div class="field-label">${escapeHtml(f)}</div><div class="field-value">${escapeHtml(val)}</div></div>`;
    }).filter(Boolean).join("");
    return `<div class="entry-block">${lines}</div>`;
  }).join("");
  return `<div class="modal-section"><h4>${escapeHtml(title)}</h4>${rows}</div>`;
}

function enterEditMode() {
  if (!_modalCV) return;
  setModalMode("edit");
  document.getElementById("cv-modal-footer").style.display = "flex";
  document.getElementById("cv-modal-body").classList.remove("chat-mode");
  renderCVEdit(_modalCV);
}

function cancelEdit() {
  if (!_modalCV) return;
  renderCVView(_modalCV);
}

function renderCVEdit(cv) {
  const body = document.getElementById("cv-modal-body");
  body.innerHTML = `
    <div class="modal-section">
      <h4>Header</h4>
      ${inputRow("Tên", "edit-name", cv.name || "")}
      ${inputRow("Email", "edit-email", cv.email || "")}
      ${inputRow("SĐT", "edit-phone", cv.phone || "")}
      ${inputRow("Năm KN", "edit-years", cv.years_exp ?? "", "number")}
    </div>
    <div class="modal-section">
      <h4>Tóm tắt</h4>
      <textarea id="edit-summary">${escapeHtml(cv.summary || "")}</textarea>
    </div>
    <div class="modal-section">
      <h4>Skills (mỗi skill phân cách bằng dấu phẩy)</h4>
      <textarea id="edit-skills">${escapeHtml((cv.skills || []).join(", "))}</textarea>
    </div>
    ${editEntriesSection("Học vấn", "education", cv.education, [["degree", "Bằng cấp"], ["school", "Trường"], ["duration", "Thời gian"]])}
    ${editEntriesSection("Kinh nghiệm", "work_history", cv.work_history, [["role", "Role"], ["company", "Công ty"], ["duration", "Thời gian"], ["description", "Mô tả", true]])}
    ${editEntriesSection("Dự án", "projects", cv.projects, [["name", "Tên"], ["description", "Mô tả", true], ["tech", "Tech (phân cách dấu phẩy)"], ["duration", "Thời gian"], ["url", "URL"]])}
    ${editEntriesSection("Giải thưởng", "awards", cv.awards, [["name", "Tên"], ["issuer", "Đơn vị"], ["year", "Năm"], ["description", "Mô tả", true]])}
    ${editEntriesSection("Chứng chỉ", "certifications", cv.certifications, [["name", "Tên"], ["issuer", "Đơn vị"], ["year", "Năm"]])}
  `;
}

function inputRow(label, id, val, type) {
  return `<div class="field-row"><div class="field-label">${escapeHtml(label)}</div><input id="${id}" type="${type || "text"}" value="${escapeHtml(val)}"/></div>`;
}

function editEntriesSection(title, section, entries, fields) {
  const list = entries || [];
  const blocks = list.map((e, i) => editEntryBlock(section, i, e, fields)).join("");
  return `<div class="modal-section" data-section="${section}">
    <h4>${escapeHtml(title)}</h4>
    <div id="entries-${section}">${blocks}</div>
    <button type="button" class="add-entry-btn" onclick="addEditEntry('${section}', ${JSON.stringify(fields).replace(/"/g, "&quot;")})">+ Thêm mục</button>
  </div>`;
}

function editEntryBlock(section, idx, entry, fields) {
  const rows = fields.map(([key, label, isTextarea]) => {
    const v = entry[key];
    const val = Array.isArray(v) ? v.join(", ") : (v ?? "");
    if (isTextarea) {
      return `<div class="field-row"><div class="field-label">${escapeHtml(label)}</div><textarea data-key="${key}">${escapeHtml(val)}</textarea></div>`;
    }
    return `<div class="field-row"><div class="field-label">${escapeHtml(label)}</div><input type="text" data-key="${key}" value="${escapeHtml(val)}"/></div>`;
  }).join("");
  return `<div class="entry-block" data-idx="${idx}">
    <button type="button" class="entry-remove" onclick="this.parentElement.remove()">✕</button>
    ${rows}
  </div>`;
}

function addEditEntry(section, fields) {
  const wrap = document.getElementById(`entries-${section}`);
  if (!wrap) return;
  const idx = wrap.children.length;
  const empty = Object.fromEntries(fields.map(([k]) => [k, ""]));
  wrap.insertAdjacentHTML("beforeend", editEntryBlock(section, idx, empty, fields));
}

function collectEntries(section, fields) {
  const wrap = document.getElementById(`entries-${section}`);
  if (!wrap) return [];
  const out = [];
  wrap.querySelectorAll(".entry-block").forEach(block => {
    const obj = {};
    fields.forEach(([k]) => {
      const el = block.querySelector(`[data-key="${k}"]`);
      let v = el ? el.value.trim() : "";
      // Tech is an array field
      if (k === "tech") v = v ? v.split(",").map(s => s.trim()).filter(Boolean) : [];
      obj[k] = v;
    });
    // Skip totally empty blocks
    if (Object.values(obj).some(v => v && (Array.isArray(v) ? v.length : true))) out.push(obj);
  });
  return out;
}

async function saveEdit() {
  if (!_modalKey) return;
  const skillsRaw = document.getElementById("edit-skills").value;
  const yearsRaw = document.getElementById("edit-years").value;
  const parsed = {
    name: document.getElementById("edit-name").value.trim(),
    email: document.getElementById("edit-email").value.trim(),
    phone: document.getElementById("edit-phone").value.trim(),
    years_exp: yearsRaw === "" ? null : Number(yearsRaw),
    skills: skillsRaw.split(",").map(s => s.trim()).filter(Boolean),
    summary: document.getElementById("edit-summary").value.trim(),
    education: collectEntries("education", [["degree"], ["school"], ["duration"]]),
    work_history: collectEntries("work_history", [["role"], ["company"], ["duration"], ["description"]]),
    projects: collectEntries("projects", [["name"], ["description"], ["tech"], ["duration"], ["url"]]),
    awards: collectEntries("awards", [["name"], ["issuer"], ["year"], ["description"]]),
    certifications: collectEntries("certifications", [["name"], ["issuer"], ["year"]]),
  };
  const sp = document.getElementById("cv-modal-save-spinner");
  sp.classList.add("show");
  try {
    await fetchJSON(`${API}/Storage/${encodeURIComponent(_modalKey)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parsed }),
    });
    closeCVModal();
    if (typeof reloadStorageView === "function") reloadStorageView();
  } catch (e) {
    alert(`Lỗi save: ${e.message}`);
  } finally {
    sp.classList.remove("show");
  }
}

function openDeleteConfirm() {
  if (!_modalKey) return;
  document.getElementById("cv-delete-name").textContent = (_modalCV && _modalCV.name) || _modalKey;
  document.getElementById("cv-delete-backdrop").classList.add("show");
}

function closeDeleteConfirm(ev) {
  if (ev && ev.target && ev.target.id !== "cv-delete-backdrop") return;
  document.getElementById("cv-delete-backdrop").classList.remove("show");
}

async function doDelete() {
  if (!_modalKey) return;
  const sp = document.getElementById("cv-delete-spinner");
  sp.classList.add("show");
  try {
    await fetchJSON(`${API}/Storage/${encodeURIComponent(_modalKey)}`, { method: "DELETE" });
    closeDeleteConfirm();
    closeCVModal();
    if (typeof reloadStorageView === "function") reloadStorageView();
  } catch (e) {
    alert(`Lỗi delete: ${e.message}`);
  } finally {
    sp.classList.remove("show");
  }
}
