// Chat in-modal: enter từ icon chat trên modal-actions
// Session ánh xạ cv_key 1:1, lưu trong localStorage để reload tab vẫn giữ history
// Phụ thuộc state từ modal.js: _modalCV, _modalKey, setModalMode()

const CHAT_LS_KEY = "chat_sessions_v1";       // { cv_key: session_id }
let _activeChatSession = null;

function _loadSessionMap() {
  try { return JSON.parse(localStorage.getItem(CHAT_LS_KEY) || "{}"); }
  catch { return {}; }
}
function _saveSessionMap(m) { localStorage.setItem(CHAT_LS_KEY, JSON.stringify(m)); }

// Gọi từ modal.js closeCVModal() để clear state khi đóng modal
function _resetActiveChatSession() { _activeChatSession = null; }

// Vào chat mode: render UI chat trong modal body, resolve session
async function enterChatMode() {
  if (!_modalCV || !_modalKey) return;
  setModalMode("chat");

  const title = document.getElementById("cv-modal-title");
  const body = document.getElementById("cv-modal-body");
  const footer = document.getElementById("cv-modal-footer");

  title.textContent = `💬 ${_modalCV.name || _modalKey}`;
  footer.style.display = "none";
  body.classList.add("chat-mode");
  body.innerHTML = `
    <div class="chat-messages" id="cv-modal-chat-messages">
      <div class="chat-empty">Đang tải session...</div>
    </div>
    <div class="chat-input-bar">
      <textarea id="cv-modal-chat-input" placeholder="Hỏi gì đó về ứng viên..." rows="1"
                onkeydown="onChatInputKey(event)"></textarea>
      <button class="btn btn-primary" id="cv-modal-chat-send-btn" onclick="sendChatMessage()">Gửi</button>
    </div>
  `;

  const map = _loadSessionMap();
  let session_id = map[_modalKey];
  try {
    if (session_id) {
      // Cố load history; nếu session đã hết hạn / bị xoá thì tạo mới
      try {
        const sess = await fetchJSON(`${API}/Chat/Sessions/${session_id}`);
        _activeChatSession = sess.session_id;
        renderChatHistory(sess.messages || []);
        return;
      } catch {
        delete map[_modalKey]; _saveSessionMap(map);
        session_id = null;
      }
    }
    const created = await fetchJSON(`${API}/Chat/Sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cv_key: _modalKey }),
    });
    _activeChatSession = created.session_id;
    map[_modalKey] = created.session_id;
    _saveSessionMap(map);
    renderChatHistory([]);
  } catch (e) {
    document.getElementById("cv-modal-chat-messages").innerHTML =
      `<div class="chat-empty" style="color:var(--danger)">Lỗi: ${escapeHtml(e.message)}</div>`;
  }
}

// Thoát chat mode về view detail
function exitChatMode() {
  if (!_modalCV) return;
  renderCVView(_modalCV);
}

function renderChatHistory(msgs) {
  const wrap = document.getElementById("cv-modal-chat-messages");
  if (!wrap) return;
  if (!msgs.length) {
    wrap.innerHTML = `<div class="chat-empty">Hỏi về kinh nghiệm, kỹ năng, học vấn, hoặc dự án của ứng viên.</div>`;
    return;
  }
  wrap.innerHTML = msgs.map(m => msgHtml(m.role, m.content, m.sources || [])).join("");
  wrap.scrollTop = wrap.scrollHeight;
}

function msgHtml(role, content, sources) {
  const srcHtml = sources && sources.length
    ? `<details class="chat-sources"><summary>${sources.length} nguồn từ CV</summary>${
        sources.map(s => `<div class="chat-source-item"><strong>[${escapeHtml(s.section)}]</strong> ${escapeHtml(s.chunk_text)} <em style="color:var(--muted)">(${(s.score || 0).toFixed(3)})</em></div>`).join("")
      }</details>` : "";
  return `<div class="chat-msg ${role}"><div class="chat-bubble">${escapeHtml(content)}</div>${srcHtml}</div>`;
}

async function resetChatSession() {
  if (!_activeChatSession || !_modalKey) return;
  if (!confirm("Xoá session chat hiện tại và bắt đầu mới?")) return;
  try {
    await fetchJSON(`${API}/Chat/Sessions/${_activeChatSession}`, { method: "DELETE" });
  } catch { /* may already be gone */ }
  const map = _loadSessionMap();
  delete map[_modalKey]; _saveSessionMap(map);
  _activeChatSession = null;
  enterChatMode();
}

function onChatInputKey(ev) {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    sendChatMessage();
  }
}

async function sendChatMessage() {
  if (!_activeChatSession) return;
  const input = document.getElementById("cv-modal-chat-input");
  const msg = input.value.trim();
  if (!msg) return;
  input.value = "";
  input.style.height = "auto";

  const wrap = document.getElementById("cv-modal-chat-messages");
  const emptyEl = wrap.querySelector(".chat-empty");
  if (emptyEl) emptyEl.remove();

  wrap.insertAdjacentHTML("beforeend", msgHtml("user", msg, []));
  const botEl = document.createElement("div");
  botEl.className = "chat-msg assistant";
  botEl.innerHTML = `<div class="chat-bubble"></div>`;
  wrap.appendChild(botEl);
  wrap.scrollTop = wrap.scrollHeight;
  const bubble = botEl.querySelector(".chat-bubble");

  const sendBtn = document.getElementById("cv-modal-chat-send-btn");
  sendBtn.disabled = true;
  input.disabled = true;

  try {
    const resp = await fetch(`${API}/Chat/Sessions/${_activeChatSession}/Messages/Stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let answerLocked = false;
    let answer = "";
    let sources = "";
    let buf = "";
    const SENTINEL = "\n__SOURCES__\n";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      // Decode 1 lần per chunk (tránh double-decode bug của bản cũ)
      const chunk = decoder.decode(value, { stream: true });
      if (!answerLocked) {
        buf += chunk;
        const idx = buf.indexOf(SENTINEL);
        if (idx >= 0) {
          answer = buf.slice(0, idx);
          sources = buf.slice(idx + SENTINEL.length);
          answerLocked = true;
        } else {
          answer = buf;
        }
      } else {
        sources += chunk;
      }
      bubble.textContent = answer;
      wrap.scrollTop = wrap.scrollHeight;
    }
    // Flush phần đuôi nếu có
    const tail = decoder.decode();
    if (tail) {
      if (answerLocked) {
        sources += tail;
      } else {
        buf += tail;
        const idx = buf.indexOf(SENTINEL);
        if (idx >= 0) {
          answer = buf.slice(0, idx);
          sources = buf.slice(idx + SENTINEL.length);
          answerLocked = true;
        } else {
          answer = buf;
        }
      }
    }
    bubble.textContent = answer;

    if (sources) {
      try {
        const arr = JSON.parse(sources);
        if (Array.isArray(arr) && arr.length) {
          botEl.insertAdjacentHTML("beforeend",
            `<details class="chat-sources"><summary>${arr.length} nguồn từ CV</summary>${
              arr.map(s => `<div class="chat-source-item"><strong>[${escapeHtml(s.section)}]</strong> ${escapeHtml(s.chunk_text)} <em style="color:var(--muted)">(${(s.score || 0).toFixed(3)})</em></div>`).join("")
            }</details>`);
        }
      } catch { /* ignore bad json */ }
    }
  } catch (e) {
    bubble.innerHTML = `<span style="color:var(--danger)">Lỗi: ${escapeHtml(e.message)}</span>`;
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
    wrap.scrollTop = wrap.scrollHeight;
  }
}
