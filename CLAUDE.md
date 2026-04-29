# CLAUDE.md

## Project Overview

Web-based Linux terminal service for internal company use. Users log in via browser and get isolated Docker containers running bash.

## Architecture

```
Browser (xterm.js)
    ↕ WSS /ws/{session_id}?token=JWT
nginx (static files + proxy)
    ↕ HTTP/WS
FastAPI backend (single uvicorn worker)
    ↕ subprocess PTY → docker exec -it <container> bash
Per-session Docker container (Ubuntu 22.04 sandbox)
    ↕ /var/run/docker.sock (DooD)
Host Docker daemon
```

## Key Technical Decisions

**Terminal bridge uses subprocess+PTY, not aiodocker exec.**
aiodocker's `read_out()` uses multiplexed framing (8-byte header) that breaks when `tty=True` because the Docker daemon sends raw bytes without headers in TTY mode. We run `docker exec -it <container_id> bash --login` as a subprocess with `pty.openpty()`, bridging master_fd to the WebSocket. Resize propagates via `TIOCSWINSZ` on master_fd → SIGWINCH to docker exec → Docker resize API → container PTY.

**bcrypt directly, not passlib.**
`passlib[bcrypt]` has a hard compatibility break with `bcrypt >= 4.0` (removed `__about__` attribute). Use the `bcrypt` library directly in `services/auth.py`.

**Single uvicorn worker is mandatory.**
`services/session_manager.active_connections` is an in-memory dict. Multiple workers would split connections across processes and break session cleanup. Do not add `--workers N` to the CMD.

**Docker socket mounted in backend container (DooD).**
The backend creates/destroys sandbox containers at runtime via the host Docker daemon. The backend runs as root in docker-compose to access `/var/run/docker.sock`.

**SSH private key support is private-key only.**
Users can save an SSH private key from the dashboard. On session creation, the backend writes it into the sandbox as `/home/sandbox/.ssh/id_rsa`. On terminal connect, `terminal_bridge.py` also injects the same value into the login shell environment as `SSH_PRIVATE_KEY`. There is no public key workflow anymore; do not reintroduce one unless there is a concrete use case.

## Common Commands

```bash
# Full rebuild and start
docker compose build && docker compose up -d

# Create first admin user
echo -e "admin\nadmin@company.com\npassword" | docker compose exec -T backend python scripts/create_admin.py

# View logs
docker compose logs -f backend

# Check active sandbox containers
docker ps --filter "label=web-terminal=sandbox"

# Run backend locally (for development, needs docker socket)
cd backend && pip install -r requirements.txt
DATABASE_URL=sqlite+aiosqlite:///./dev.db uvicorn main:app --reload
```

## Directory Structure

```
backend/
  main.py               # FastAPI app, lifespan (DB init + cleanup loop)
  config.py             # Settings via pydantic-settings (reads .env)
  database.py           # aiosqlite, schema, get_db dependency
  models/               # Pydantic request/response shapes
  routers/              # FastAPI route handlers (thin — logic lives in services)
  services/
    auth.py             # bcrypt hash/verify, JWT create/decode
    docker_manager.py   # Container create/destroy/status via aiodocker
    session_manager.py  # Session CRUD + cleanup loop + active_connections dict
    terminal_bridge.py  # WebSocket ↔ PTY bridge (THE critical file)
  middleware/auth.py    # get_current_user / require_admin FastAPI Depends
  scripts/create_admin.py

sandbox/Dockerfile      # Ubuntu 22.04, sandbox user (uid 1001), common tools
frontend/               # Pure HTML/CSS/JS, served by nginx, no build step
  dashboard.html        # Session list + SSH private key management UI
nginx/nginx.conf        # Static files + /api/ and /ws/ proxy with WS upgrade
data/                   # SQLite DB volume mount
```

## Environment Variables

See `.env.example`. Key ones:
- `SECRET_KEY` — JWT signing key, generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `IDLE_TIMEOUT` — seconds before idle session is terminated (default 1800)
- `MAX_SESSION_TIME` — hard session limit in seconds (default 14400)
- `CONTAINER_MEMORY` / `CONTAINER_CPUS` / `CONTAINER_PIDS_LIMIT` — sandbox resource limits

## Adding Tools to the Sandbox

Edit `sandbox/Dockerfile`, add `apt-get install -y <package>`, then:
```bash
docker compose build  # rebuilds sandbox image
# New sessions get the new image; existing containers are unaffected
```

## WebSocket Message Protocol

Client → Server:
```json
{"type": "input",  "data": "ls -la\r"}
{"type": "resize", "cols": 204, "rows": 52}
{"type": "ping"}
```

Server → Client:
```json
{"type": "connected", "session_id": "uuid"}
{"type": "output",    "data": "...terminal bytes..."}
{"type": "pong"}
{"type": "terminated","reason": "idle_timeout|max_session_time|user_request|admin_terminated|server_shutdown"}
```

## Database Schema

Two tables: `users` and `sessions`. SQLite at `/data/web_terminal.db` (volume-mounted from `./data/`). Schema is auto-created at startup in `database.py:init_db()`. No migration tooling — for schema changes, drop and recreate (internal tool, no persistent user data worth preserving).

Current user SSH state is stored in `users.ssh_private_key`.

Relevant routes:
- `GET /api/auth/me` — includes `has_ssh_key`
- `GET /api/profile/ssh-key` — returns whether the current user has a saved private key
- `PUT /api/profile/ssh-key` — save or replace the private key
- `DELETE /api/profile/ssh-key` — remove the saved private key

## Security Notes

- Sandbox containers run as user `sandbox` (uid 1001), non-root
- Capabilities dropped: NET_RAW, SYS_ADMIN, MKNOD
- `no-new-privileges` seccomp option prevents privilege escalation
- Sandbox network is `Internal: True` — no outbound internet from containers
- To enable internet in containers: remove `"Internal": True` from `docker_manager.py:ensure_sandbox_network()`
