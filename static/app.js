const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const formEl = document.getElementById("input-form");
const connectionDot = document.getElementById("connection-dot");
const connectionText = document.getElementById("connection-text");
const stateEl = document.getElementById("ableton-state");
const tracksEl = document.getElementById("tracks-list");
const presetsEl = document.getElementById("presets-list");
const resetBtn = document.getElementById("reset-btn");

let ws = null;
let currentAssistantMsg = null;
let isProcessing = false;

// --- WebSocket ---
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    connectionDot.classList.add("connected");
    connectionText.textContent = "Connected";
  };

  ws.onclose = () => {
    connectionDot.classList.remove("connected");
    connectionText.textContent = "Disconnected";
    setTimeout(connect, 3000);
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  };
}

function handleMessage(msg) {
  switch (msg.type) {
    case "text":
      if (!currentAssistantMsg) {
        currentAssistantMsg = addMessage("assistant", "");
      }
      appendToMessage(currentAssistantMsg, msg.content);
      break;

    case "tool_call":
      if (!currentAssistantMsg) {
        currentAssistantMsg = addMessage("assistant", "");
      }
      const badge = document.createElement("span");
      badge.className = "tool-badge pending";
      badge.id = `tool-${msg.name}-${Date.now()}`;
      badge.textContent = `${msg.name}`;
      currentAssistantMsg.appendChild(badge);
      currentAssistantMsg.appendChild(document.createTextNode(" "));
      scrollToBottom();
      break;

    case "tool_result": {
      // Mark the last pending badge as done
      const badges = currentAssistantMsg.querySelectorAll(".tool-badge.pending");
      if (badges.length > 0) {
        const last = badges[badges.length - 1];
        last.classList.remove("pending");
        last.innerHTML = `${msg.name} <span class="check">✓</span>`;
      }
      scrollToBottom();
      break;
    }

    case "done":
      currentAssistantMsg = null;
      isProcessing = false;
      sendBtn.disabled = false;
      inputEl.focus();
      break;

    case "error":
      addMessage("error", msg.content);
      currentAssistantMsg = null;
      isProcessing = false;
      sendBtn.disabled = false;
      break;

    case "ableton_state":
      updateAbletonState(msg.data);
      break;
  }
}

// --- Messages ---
function addMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  if (role === "error") {
    div.className = "message error-msg";
  }
  if (content) {
    div.innerHTML = formatText(content);
  }
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

function appendToMessage(el, text) {
  // Append text, converting newlines to <br>
  const parts = text.split("\n");
  for (let i = 0; i < parts.length; i++) {
    if (i > 0) el.appendChild(document.createElement("br"));
    if (parts[i]) el.appendChild(document.createTextNode(parts[i]));
  }
  scrollToBottom();
}

function formatText(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.*?)`/g, '<code style="background:#2a2a3e;padding:1px 4px;border-radius:3px;font-size:12px">$1</code>');
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Send ---
function sendMessage(text) {
  if (!text.trim() || isProcessing || !ws) return;

  addMessage("user", text);
  ws.send(JSON.stringify({ type: "chat", content: text }));
  inputEl.value = "";
  isProcessing = true;
  sendBtn.disabled = true;
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(inputEl.value);
});

// --- Ableton State ---
function updateAbletonState(state) {
  if (!state.connected) {
    stateEl.innerHTML = '<div class="state-row"><span class="state-label">Ableton</span><span class="state-value" style="color:var(--red)">Not connected</span></div>';
    tracksEl.innerHTML = "";
    connectionDot.classList.remove("connected");
    return;
  }

  stateEl.innerHTML = `
    <div class="state-row"><span class="state-label">Tempo</span><span class="state-value">${state.tempo} BPM</span></div>
    <div class="state-row"><span class="state-label">Time Sig</span><span class="state-value">${state.time_sig}</span></div>
    <div class="state-row"><span class="state-label">Tracks</span><span class="state-value">${state.track_count}</span></div>
    <div class="state-row"><span class="state-label">Master</span><span class="state-value">${(state.master_volume * 100).toFixed(0)}%</span></div>
  `;

  tracksEl.innerHTML = "";
  for (const track of state.tracks || []) {
    const div = document.createElement("div");
    div.className = `track-item${track.arm ? " armed" : ""}`;
    const type = track.is_audio ? "AUD" : "MID";
    const pan = track.panning === 0 ? "C" : (track.panning < 0 ? `${Math.round(track.panning * -100)}L` : `${Math.round(track.panning * 100)}R`);
    div.innerHTML = `
      <div class="track-name">${track.name}</div>
      <div class="track-detail">${type} · Vol ${Math.round(track.volume * 100)}% · Pan ${pan}${track.arm ? " · ARM" : ""}${track.mute ? " · MUTE" : ""}${track.solo ? " · SOLO" : ""}</div>
      <div class="track-detail">${track.devices.join(" → ") || "No devices"}</div>
    `;
    tracksEl.appendChild(div);
  }
}

// --- Presets ---
async function loadPresets() {
  try {
    const resp = await fetch("/api/presets");
    const presets = await resp.json();
    presetsEl.innerHTML = "";
    for (const p of presets) {
      const btn = document.createElement("button");
      btn.className = "preset-btn";
      btn.textContent = p.name;
      btn.title = p.description;
      btn.onclick = () => sendMessage(`Apply the "${p.id}" preset`);
      presetsEl.appendChild(btn);
    }
  } catch (e) {
    console.error("Failed to load presets:", e);
  }
}

// --- Reset ---
resetBtn.addEventListener("click", () => {
  if (ws) {
    ws.send(JSON.stringify({ type: "reset" }));
    messagesEl.innerHTML = "";
  }
});

// --- Init ---
async function init() {
  connect();
  loadPresets();

  const resp = await fetch("/api/key-status");
  const data = await resp.json();

  if (!data.has_key) {
    const div = document.createElement("div");
    div.className = "message assistant";
    div.innerHTML = `
      <strong>Welcome to GMartin Produce!</strong><br><br>
      One-time setup: paste your Anthropic API key below.<br>
      <a href="https://console.anthropic.com/settings/keys" target="_blank" style="color:var(--accent)">Get one here</a> (free tier available)<br><br>
      <input type="password" id="api-key-input" placeholder="sk-ant-..." style="width:100%;padding:10px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:14px;margin-bottom:8px">
      <button onclick="submitApiKey()" style="padding:8px 20px;background:var(--accent);color:#000;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:14px">Start Producing</button>
      <span id="key-error" style="color:var(--red);font-size:12px;margin-left:8px"></span>
    `;
    messagesEl.appendChild(div);
  } else {
    addMessage("assistant", "Hey! I'm <strong>GMartin</strong>, your music production assistant. I can control Ableton Live, build sessions, tweak effects, and help you produce.\n\nTry: <em>\"Set up an indie rock session\"</em> or <em>\"Add more reverb to guitar L\"</em>");
  }
}

async function submitApiKey() {
  const input = document.getElementById("api-key-input");
  const error = document.getElementById("key-error");
  const key = input.value.trim();
  if (!key) { error.textContent = "Please enter a key"; return; }

  const resp = await fetch("/api/set-key", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({key})
  });
  const data = await resp.json();
  if (data.ok) {
    messagesEl.innerHTML = "";
    addMessage("assistant", "Let's go! I'm <strong>GMartin</strong>, your music production assistant. I can control Ableton Live, build sessions, tweak effects, and help you produce.\n\nTry: <em>\"Set up an indie rock session\"</em> or <em>\"Add more reverb to guitar L\"</em>");
  } else {
    error.textContent = data.error || "Failed to save key";
  }
}

init();
