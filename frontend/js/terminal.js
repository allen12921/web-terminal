const HEARTBEAT_INTERVAL = 25000;

let term, fitAddon, ws, sessionId;
let ageStart, ageTimer, heartbeatTimer;
let reconnectAllowed = true;

document.addEventListener("DOMContentLoaded", async () => {
  if (!getToken()) {
    window.location.href = "/index.html";
    return;
  }

  const params = new URLSearchParams(location.search);
  sessionId = params.get("s");
  if (!sessionId) {
    window.location.href = "/dashboard.html";
    return;
  }

  document.getElementById("session-id-display").textContent = sessionId.substring(0, 8) + "…";

  try {
    const sshKeyStatus = await apiFetch("/api/profile/ssh-key");
    if (sshKeyStatus?.has_private_key) {
      const hint = document.getElementById("ssh-env-hint");
      hint.textContent = "SSH_PRIVATE_KEY available in this shell";
      hint.style.display = "inline";
    }
  } catch {}

  initTerminal();
  connect();

  document.getElementById("disconnect-btn").addEventListener("click", () => {
    reconnectAllowed = false;
    if (ws) ws.close();
    window.location.href = "/dashboard.html";
  });

  window.addEventListener("resize", () => fitAddon && fitAddon.fit());
});

function initTerminal() {
  term = new Terminal({
    fontFamily: '"Cascadia Code", "Fira Code", "JetBrains Mono", "SFMono-Regular", Menlo, monospace',
    fontSize: 14,
    lineHeight: 1.2,
    cursorBlink: true,
    theme: {
      background: "#000000",
      foreground: "#e6edf3",
      cursor: "#e6edf3",
      selectionBackground: "rgba(88,166,255,0.3)",
      black: "#484f58",
      red: "#ff7b72",
      green: "#3fb950",
      yellow: "#e3b341",
      blue: "#58a6ff",
      magenta: "#d2a8ff",
      cyan: "#39d353",
      white: "#b1bac4",
      brightBlack: "#6e7681",
      brightRed: "#ffa198",
      brightGreen: "#56d364",
      brightYellow: "#e3b341",
      brightBlue: "#79c0ff",
      brightMagenta: "#d2a8ff",
      brightCyan: "#56d364",
      brightWhite: "#f0f6fc",
    },
    allowTransparency: true,
  });

  fitAddon = new FitAddon.FitAddon();
  const webLinksAddon = new WebLinksAddon.WebLinksAddon();
  term.loadAddon(fitAddon);
  term.loadAddon(webLinksAddon);

  const container = document.getElementById("terminal-container");
  term.open(container);
  fitAddon.fit();

  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data }));
    }
  });

  term.onResize(({ cols, rows }) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "resize", cols, rows }));
    }
  });
}

function connect() {
  setStatus("connecting");
  const url = wsUrl(`/ws/${sessionId}`);
  ws = new WebSocket(url);

  ws.onopen = () => {
    setStatus("connected");
    startHeartbeat();
    term.focus();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "output") {
        term.write(msg.data);
      } else if (msg.type === "connected") {
        ageStart = Date.now();
        startAgeCounter();
        // Send initial size
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      } else if (msg.type === "terminated") {
        showOverlay(msg.reason || "session_ended");
      } else if (msg.type === "pong") {
        // heartbeat ack
      }
    } catch {}
  };

  ws.onclose = (e) => {
    setStatus("disconnected");
    stopHeartbeat();
    if (reconnectAllowed && e.code !== 4001 && e.code !== 4004) {
      term.write("\r\n\x1b[33m[Disconnected. Reconnecting in 3s…]\x1b[0m\r\n");
      setTimeout(connect, 3000);
    } else if (e.code === 4004) {
      showOverlay("session_not_found");
    }
  };

  ws.onerror = () => setStatus("disconnected");
}

function startHeartbeat() {
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, HEARTBEAT_INTERVAL);
}

function stopHeartbeat() {
  clearInterval(heartbeatTimer);
}

function startAgeCounter() {
  clearInterval(ageTimer);
  ageTimer = setInterval(() => {
    if (!ageStart) return;
    const secs = Math.floor((Date.now() - ageStart) / 1000);
    const h = Math.floor(secs / 3600).toString().padStart(2, "0");
    const m = Math.floor((secs % 3600) / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    document.getElementById("age-counter").textContent = `${h}:${m}:${s}`;
  }, 1000);
}

function setStatus(state) {
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  dot.className = "status-dot";
  if (state === "connected") {
    dot.classList.add("connected");
    label.textContent = "Connected";
  } else if (state === "connecting") {
    dot.classList.add("connecting");
    label.textContent = "Connecting…";
  } else {
    dot.classList.add("disconnected");
    label.textContent = "Disconnected";
  }
}

function showOverlay(reason) {
  reconnectAllowed = false;
  stopHeartbeat();
  clearInterval(ageTimer);

  const messages = {
    idle_timeout: "Session ended: idle timeout (30 min)",
    max_session_time: "Session ended: maximum time reached (4 hours)",
    admin_terminated: "Session was terminated by an administrator",
    user_request: "Session terminated",
    server_shutdown: "Server is shutting down",
    session_ended: "Terminal session has ended",
    session_not_found: "Session not found or already terminated",
  };

  document.getElementById("overlay-reason").textContent = messages[reason] || reason;
  document.getElementById("terminal-overlay").classList.add("visible");
}
