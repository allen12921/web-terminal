document.addEventListener("DOMContentLoaded", async () => {
  // Redirect if already logged in
  const token = getToken();
  if (token) {
    try {
      await apiFetch("/api/auth/me");
      window.location.href = "/dashboard.html";
      return;
    } catch {}
  }

  const form = document.getElementById("login-form");
  const errorEl = document.getElementById("login-error");
  const btnEl = document.getElementById("login-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.style.display = "none";
    btnEl.disabled = true;
    btnEl.textContent = "Signing in…";

    const body = new URLSearchParams({
      username: document.getElementById("username").value,
      password: document.getElementById("password").value,
    });

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });

      if (!res.ok) {
        let msg = "Login failed";
        try { msg = (await res.json()).detail || msg; } catch {}
        errorEl.textContent = msg;
        errorEl.style.display = "block";
        return;
      }

      const data = await res.json();
      setToken(data.access_token);
      window.location.href = "/dashboard.html";
    } catch (err) {
      errorEl.textContent = err.message || "Network error";
      errorEl.style.display = "block";
    } finally {
      btnEl.disabled = false;
      btnEl.textContent = "Sign in";
    }
  });
});
