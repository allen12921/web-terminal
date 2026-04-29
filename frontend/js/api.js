const API_BASE = "";

function getToken() {
  return localStorage.getItem("wt_token");
}

function setToken(token) {
  localStorage.setItem("wt_token", token);
}

function clearToken() {
  localStorage.removeItem("wt_token");
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API_BASE + path, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    window.location.href = "/index.html";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}?token=${getToken()}`;
}
