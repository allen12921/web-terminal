# Web Terminal

基于浏览器的 Linux 终端服务，供公司内部使用。每位用户可获得一个独立的 Docker 容器，直接在浏览器中使用完整的 bash 环境。

**灵感来源于 [webminal.org](https://www.webminal.org/)**，但采用现代技术栈重新构建。

## 功能特性

- **浏览器终端** — xterm.js，支持完整颜色、Tab 补全、vim/nano
- **隔离沙箱** — 每个会话独享一个 Docker 容器（256MB 内存，0.5 CPU）
- **会话管理** — 闲置 30 分钟自动终止，最长使用 4 小时
- **用户管理** — 管理员面板可创建用户、强制终止会话
- **断线重连** — 断开连接后容器保持运行，可随时重新连接
- **无需构建** — 前端为纯 HTML/CSS/JS，由 nginx 直接托管

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | Vanilla JS + [xterm.js](https://xtermjs.org/) 5.5（CDN） |
| 后端 | Python 3.11 + FastAPI |
| 终端 | subprocess PTY → `docker exec -it` |
| 隔离 | 每会话一个 Docker 容器 |
| 认证 | JWT（HS256）+ bcrypt |
| 存储 | SQLite |
| 代理 | nginx |
| 部署 | Docker Compose |

## 快速开始

**前置条件：** Docker Desktop（或 Docker Engine + Compose 插件）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，将 SECRET_KEY 设置为随机字符串
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

# 2. 构建并启动
docker compose build
docker compose up -d

# 3. 创建第一个管理员账号
echo -e "admin\nadmin@yourcompany.com\nyourpassword" | \
  docker compose exec -T backend python scripts/create_admin.py

# 4. 在浏览器中打开
open http://localhost
```

## 使用说明

### 普通用户

1. 访问 `http://your-server`，使用账号登录
2. 点击 **New Terminal** 创建会话
3. 浏览器中打开 bash 终端，像使用普通 Linux shell 一样操作
4. 点击 **Disconnect** 或关闭标签页断开连接（容器保持运行，可重新连接）
5. 闲置 30 分钟后会话自动终止

### 管理员

点击右上角 **Admin**（仅管理员账号可见）：
- 创建或停用用户账号
- 将用户升级为管理员
- 查看并强制终止任意会话

### 通过 API 创建用户

```bash
# 也可在管理员面板中操作，或通过 API：
curl -X POST http://localhost/api/admin/users \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@co.com","password":"pass123","is_admin":false}'
```

## 配置项

所有配置在 `.env` 文件中（从 `.env.example` 复制）：

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `SECRET_KEY` | *（必填）* | JWT 签名密钥，用 `python3 -c "import secrets; print(secrets.token_hex(32))"` 生成 |
| `PORT` | `80` | nginx 监听端口 |
| `IDLE_TIMEOUT` | `1800` | 闲置超时秒数（30 分钟） |
| `MAX_SESSION_TIME` | `14400` | 会话最长时间秒数（4 小时） |
| `MAX_SESSIONS_PER_USER` | `3` | 每用户最大并发会话数 |
| `CONTAINER_MEMORY` | `256m` | 每个沙箱容器的内存限制 |
| `CONTAINER_CPUS` | `0.5` | 每个沙箱容器的 CPU 份额 |
| `CONTAINER_PIDS_LIMIT` | `50` | 每个容器的 PID 上限（防止 fork 炸弹） |

## 沙箱内置工具

每个终端会话使用 Ubuntu 22.04 容器，预装以下工具：

- **Shell：** bash + bash-completion
- **编辑器：** vim、nano
- **文件工具：** less、tree、find、file
- **文本处理：** grep、awk、sed
- **网络工具：** curl、wget、netcat、ping、dig、net-tools
- **开发工具：** git、python3、pip
- **压缩工具：** tar、gzip、zip、unzip
- **其他：** man 手册、sudo（容器内）

容器以 `sandbox` 用户（非 root）运行，已限制危险能力，默认禁止访问外网。

### 向沙箱添加软件包

编辑 `sandbox/Dockerfile`，然后重新构建：

```bash
docker compose build
# 新会话将使用更新后的镜像，已有容器不受影响
```

### 开启容器访问外网

在 `backend/services/docker_manager.py` 的 `ensure_sandbox_network()` 函数中，删除网络创建时的 `"Internal": True`，然后重新构建后端：

```bash
docker compose build backend && docker compose up -d backend
```

## API 接口

```
POST   /api/auth/login              # 表单：username + password → JWT
GET    /api/auth/me                 # 当前用户信息

POST   /api/sessions                # 创建会话（启动容器）
GET    /api/sessions                # 列出当前用户的活跃会话
GET    /api/sessions/{id}           # 查询会话状态
DELETE /api/sessions/{id}           # 终止会话

GET    /api/admin/users             # [管理员] 列出所有用户
POST   /api/admin/users             # [管理员] 创建用户
PUT    /api/admin/users/{id}        # [管理员] 修改用户（启用/停用/设管理员）
GET    /api/admin/sessions          # [管理员] 所有活跃会话
DELETE /api/admin/sessions/{id}     # [管理员] 强制终止任意会话

WS     /ws/{session_id}?token=JWT   # 终端 WebSocket
GET    /health                      # 健康检查
```

## 部署注意事项

### 放在反向代理后面（Caddy / Traefik 等）

确保转发 WebSocket 升级请求头：

```
Upgrade: websocket
Connection: Upgrade
```

内部的 nginx 已对 `/ws/` 路径做了正确配置。如果在前面再加一层代理，需确保其正确转发 WebSocket 连接。

### HTTPS

生产环境请在外层反向代理处终止 TLS（或修改 `nginx/nginx.conf` 添加 HTTPS）。HTTP 下 JWT 和密码均为明文传输——**生产环境必须启用 HTTPS**。

### 数据持久化

- SQLite 数据库存储在 `./data/web_terminal.db`（卷挂载）
- 会话容器为临时性的，终止后销毁
- 用户账号和会话记录在重启后保留

### 资源规划

每个活跃会话最多占用宿主机 256MB 内存 + 0.5 CPU（不是后端容器内）：
- 10 个并发用户：约 2.5GB 内存，约 5 个 CPU 核心
- 可在 `.env` 中调整 `CONTAINER_MEMORY` 和 `CONTAINER_CPUS`

## 常见问题

**终端连接成功但没有输出**
```bash
docker compose logs backend --tail=50
docker ps --filter "label=web-terminal=sandbox"
```

**连接时提示"Container not running"**

沙箱容器异常退出，检查：
```bash
docker compose logs backend | grep "container"
```

**会话没有自动清理**

清理循环每 60 秒运行一次，检查是否正常：
```bash
docker compose logs backend | grep -i "cleanup\|terminate"
```

**docker.sock 权限拒绝**

在 Linux 上，后端容器需要访问 Docker socket。Compose 文件中后端以 root 运行。如果修改过此配置，检查 socket 权限：
```bash
ls -la /var/run/docker.sock
```

## 许可

[MIT](./LICENSE)
