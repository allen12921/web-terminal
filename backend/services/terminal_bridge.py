import asyncio
import fcntl
import json
import os
import pty
import struct
import termios
from typing import Optional
from fastapi import WebSocket
import services.session_manager as sm


async def run_terminal(
    websocket: WebSocket,
    session_id: str,
    container_id: str,
    ssh_private_key: Optional[str] = None,
):
    await websocket.accept()
    sm.active_connections[session_id] = websocket

    loop = asyncio.get_event_loop()
    master_fd: int | None = None
    proc: asyncio.subprocess.Process | None = None

    try:
        master_fd, slave_fd = pty.openpty()
        _set_winsize(master_fd, 24, 80)

        docker_exec_cmd = ["docker", "exec", "-it"]
        if ssh_private_key:
            docker_exec_cmd += ["-e", f"SSH_PRIVATE_KEY={ssh_private_key.strip()}"]
        docker_exec_cmd += [container_id, "bash", "--login"]

        proc = await asyncio.create_subprocess_exec(
            *docker_exec_cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
        )
        os.close(slave_fd)

        await websocket.send_json({"type": "connected", "session_id": session_id})

        read_queue: asyncio.Queue[bytes] = asyncio.Queue()

        def on_readable():
            try:
                data = os.read(master_fd, 4096)
                read_queue.put_nowait(data if data else b"")
            except OSError:
                read_queue.put_nowait(b"")

        loop.add_reader(master_fd, on_readable)

        async def container_to_ws():
            while True:
                data = await read_queue.get()
                if not data:
                    break
                await websocket.send_json({
                    "type": "output",
                    "data": data.decode("utf-8", errors="replace"),
                })

        async def ws_to_container():
            async for raw in websocket.iter_text():
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mtype = msg.get("type")
                if mtype == "input":
                    payload = msg.get("data", "")
                    if isinstance(payload, str):
                        payload = payload.encode()
                    try:
                        os.write(master_fd, payload)
                    except OSError:
                        break
                    await sm.touch_session(session_id)
                elif mtype == "resize":
                    cols = int(msg.get("cols", 80))
                    rows = int(msg.get("rows", 24))
                    _set_winsize(master_fd, rows, cols)
                    await sm.touch_session(session_id)
                elif mtype == "ping":
                    await sm.touch_session(session_id)
                    await websocket.send_json({"type": "pong"})

        read_task = asyncio.create_task(container_to_ws())
        write_task = asyncio.create_task(ws_to_container())

        done, pending = await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    except Exception:
        pass
    finally:
        if master_fd is not None:
            loop.remove_reader(master_fd)
            try:
                os.close(master_fd)
            except OSError:
                pass
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        sm.active_connections.pop(session_id, None)
        try:
            await websocket.send_json({"type": "terminated", "reason": "session_ended"})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


def _set_winsize(fd: int, rows: int, cols: int):
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except Exception:
        pass
