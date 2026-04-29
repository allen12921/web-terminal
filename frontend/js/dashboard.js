let currentUser = null;
let pollTimer = null;

document.addEventListener("DOMContentLoaded", async () => {
  if (!getToken()) {
    window.location.href = "/index.html";
    return;
  }

  try {
    currentUser = await apiFetch("/api/auth/me");
  } catch {
    return;
  }

  document.getElementById("nav-username").textContent = currentUser.username;
  if (currentUser.is_admin) {
    document.getElementById("admin-link").style.display = "inline-flex";
  }

  document.getElementById("logout-btn").addEventListener("click", () => {
    clearToken();
    window.location.href = "/index.html";
  });

  document.getElementById("new-terminal-btn").addEventListener("click", createSession);

  await loadSessions();
  pollTimer = setInterval(loadSessions, 8000);
});

async function loadSessions() {
  try {
    const sessions = await apiFetch("/api/sessions");
    renderSessions(sessions);
  } catch {}
}

function renderSessions(sessions) {
  const tbody = document.getElementById("sessions-tbody");
  const empty = document.getElementById("sessions-empty");

  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = "";
    empty.style.display = "block";
    return;
  }

  empty.style.display = "none";
  tbody.innerHTML = sessions.map(s => `
    <tr>
      <td><span class="mono">${s.id.substring(0, 8)}…</span></td>
      <td>${statusBadge(s.status)}</td>
      <td>${formatDate(s.created_at)}</td>
      <td>${timeAgo(s.last_activity)}</td>
      <td>
        <div style="display:flex;gap:6px;align-items:center">
          <a href="/terminal.html?s=${s.id}" class="btn btn-sm btn-primary">Connect</a>
          <button class="btn btn-sm btn-danger" onclick="terminateSession('${s.id}')">Terminate</button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function createSession() {
  const btn = document.getElementById("new-terminal-btn");
  btn.disabled = true;
  btn.textContent = "Creating…";
  const errEl = document.getElementById("create-error");
  errEl.style.display = "none";

  try {
    const session = await apiFetch("/api/sessions", { method: "POST" });
    window.location.href = `/terminal.html?s=${session.id}`;
  } catch (err) {
    errEl.textContent = err.message || "Failed to create session";
    errEl.style.display = "block";
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 2a.75.75 0 0 1 .75.75v4.5h4.5a.75.75 0 0 1 0 1.5h-4.5v4.5a.75.75 0 0 1-1.5 0v-4.5h-4.5a.75.75 0 0 1 0-1.5h4.5v-4.5A.75.75 0 0 1 8 2Z"/></svg> New Terminal`;
  }
}

async function terminateSession(id) {
  if (!confirm("Terminate this session?")) return;
  try {
    await apiFetch(`/api/sessions/${id}`, { method: "DELETE" });
    await loadSessions();
  } catch (err) {
    alert(err.message || "Failed to terminate");
  }
}

function statusBadge(status) {
  const map = {
    active: ["badge-green", "Active"],
    idle: ["badge-yellow", "Idle"],
    pending: ["badge-yellow", "Starting"],
    terminated: ["badge-gray", "Terminated"],
  };
  const [cls, label] = map[status] || ["badge-gray", status];
  return `<span class="badge ${cls}">${label}</span>`;
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function timeAgo(iso) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  const diff = Math.floor((Date.now() - d) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}
