# Web Terminal

A browser-based Linux terminal service for internal use. Each user gets an isolated Docker container with a full bash environment accessible directly from the browser.

**Inspired by [webminal.org](https://www.webminal.org/)**, but built with a modern stack.

## Features

- **In-browser terminal** — xterm.js with full color support, tab completion, and vim/nano
- **Isolated sandboxes** — each session runs in its own Docker container (256MB RAM, 0.5 CPU)
- **Session management** — auto-terminates idle sessions (30 min), hard limit of 4 hours
- **User management** — admin panel to create users and force-terminate sessions
- **Reconnect support** — container stays alive on disconnect; reconnect to the same session
- **SSH private key injection** — users can save an SSH private key from the web UI for new sessions
- **No build step** — frontend is plain HTML/CSS/JS served by nginx

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS + [xterm.js](https://xtermjs.org/) 5.5 (CDN) |
| Backend | Python 3.11 + FastAPI |
| Terminal | subprocess PTY → `docker exec -it` |
| Isolation | Docker container per session |
| Auth | JWT (HS256) + bcrypt |
| Storage | SQLite |
| Proxy | nginx |
| Deploy | Docker Compose |

## Quick Start

**Prerequisites:** Docker Desktop (or Docker Engine + Compose plugin)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env: set SECRET_KEY to a random hex string
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

# 2. Build and start
docker compose build
docker compose up -d

# 3. Create the first admin user
echo -e "admin\nadmin@yourcompany.com\nyourpassword" | \
  docker compose exec -T backend python scripts/create_admin.py

# 4. Open in browser
open http://localhost
```

## Usage

### For users

1. Go to `http://your-server` and sign in
2. Click **New Terminal** to create a session
3. A bash terminal opens in your browser — use it like any Linux shell
4. Click **Disconnect** or close the tab to disconnect (session stays alive for reconnect)
5. Sessions idle for 30 minutes are automatically terminated
6. Optional: save an SSH private key on the dashboard; new shells will load it into the container, and it is exposed as `SSH_PRIVATE_KEY`

### For admins

Go to **Admin** (top-right, visible to admin accounts) to:
- Create or deactivate user accounts
- Promote users to admin
- View and force-terminate any active session

### Creating additional users

```bash
# Via admin panel in the browser, or via API:
curl -X POST http://localhost/api/admin/users \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@co.com","password":"pass123","is_admin":false}'
```

## Configuration

All settings are in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | JWT signing secret — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `PORT` | `80` | Host port for nginx |
| `IDLE_TIMEOUT` | `1800` | Seconds before idle session is terminated (30 min) |
| `MAX_SESSION_TIME` | `14400` | Hard session time limit in seconds (4 hours) |
| `MAX_SESSIONS_PER_USER` | `3` | Max concurrent sessions per user |
| `CONTAINER_MEMORY` | `256m` | Memory limit per sandbox container |
| `CONTAINER_CPUS` | `0.5` | CPU share per sandbox container |
| `CONTAINER_PIDS_LIMIT` | `50` | PID limit per sandbox container (prevents fork bombs) |

## What's in the Sandbox

Each terminal session gets an Ubuntu 22.04 container with:

- **Shells:** bash + bash-completion
- **Editors:** vim, nano
- **File tools:** less, tree, find, file
- **Text processing:** grep, awk, sed
- **Network:** curl, wget, netcat, ping, dig, net-tools
- **Development:** git, python3, pip
- **Archives:** tar, gzip, zip, unzip
- **Misc:** man pages, sudo (within container)

Containers run as user `sandbox` (non-root) with dropped capabilities and no outbound internet access by default.

### Adding packages to the sandbox

Edit `sandbox/Dockerfile`, then rebuild:

```bash
docker compose build
# New sessions will use the updated image
```

### Enabling internet access in containers

In `backend/services/docker_manager.py`, in `ensure_sandbox_network()`, remove `"Internal": True` from the network creation call. Rebuild the backend:

```bash
docker compose build backend && docker compose up -d backend
```

## API Reference

```
POST   /api/auth/login              # Form: username + password → JWT
GET    /api/auth/me                 # Current user profile

GET    /api/profile/ssh-key         # SSH private key presence status for current user
PUT    /api/profile/ssh-key         # Save/replace the SSH private key
DELETE /api/profile/ssh-key         # Delete the saved SSH private key

POST   /api/sessions                # Create session (starts a container)
GET    /api/sessions                # List your active sessions
GET    /api/sessions/{id}           # Session status
DELETE /api/sessions/{id}           # Terminate session

GET    /api/admin/users             # [admin] List all users
POST   /api/admin/users             # [admin] Create user
PUT    /api/admin/users/{id}        # [admin] Update user (activate/deactivate/admin)
GET    /api/admin/sessions          # [admin] All active sessions
DELETE /api/admin/sessions/{id}     # [admin] Force-terminate any session

WS     /ws/{session_id}?token=JWT   # Terminal WebSocket
GET    /health                      # Health check
```

## Deployment Notes

### Behind a reverse proxy (Caddy/Traefik/etc.)

Make sure WebSocket upgrade headers are forwarded:

```
Upgrade: websocket
Connection: Upgrade
```

The nginx inside the stack already handles this for the `/ws/` path. If you put another proxy in front, configure it to proxy-pass WebSocket connections.

### HTTPS

For production, terminate TLS at your outer reverse proxy (or modify `nginx/nginx.conf` to add HTTPS). The JWT tokens and passwords are sent in plaintext over HTTP — **use HTTPS in production**.

### Data persistence

- The SQLite database is stored at `./data/web_terminal.db` (volume-mounted)
- Session containers are ephemeral — destroyed on termination
- User accounts and session history persist across restarts

### Resource planning

Each active session uses up to 256MB RAM + 0.5 CPU on the **host** (not in the backend container). Plan accordingly:
- 10 concurrent users: ~2.5GB RAM, ~5 CPU cores
- Adjust `CONTAINER_MEMORY` and `CONTAINER_CPUS` in `.env` as needed

## Troubleshooting

**Terminal connects but shows no output**
```bash
docker compose logs backend --tail=50
docker ps --filter "label=web-terminal=sandbox"
```

**"Container not running" when connecting**
The sandbox container crashed. Check:
```bash
docker compose logs backend | grep "container"
```

**Sessions not cleaning up**
The cleanup loop runs every 60 seconds. Check it's running:
```bash
docker compose logs backend | grep -i "cleanup\|terminate"
```

**docker.sock permission denied**
On Linux, the backend container needs access to the Docker socket. The compose file runs the backend as root. If you've modified this, check socket permissions:
```bash
ls -la /var/run/docker.sock
```

## License

[MIT](./LICENSE)
