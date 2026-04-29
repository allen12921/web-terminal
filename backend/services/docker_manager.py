import asyncio
import base64
import aiodocker
from aiodocker.docker import Docker
from config import settings

_docker: Docker = None


async def get_docker() -> Docker:
    global _docker
    if _docker is None:
        _docker = aiodocker.Docker()
    return _docker


async def close_docker():
    global _docker
    if _docker:
        await _docker.close()
        _docker = None


async def ensure_sandbox_network():
    docker = await get_docker()
    try:
        await docker.networks.get(settings.sandbox_network)
    except aiodocker.exceptions.DockerError:
        await docker.networks.create({
            "Name": settings.sandbox_network,
#            "Internal": True,
            "Driver": "bridge",
            "Labels": {"web-terminal": "network"},
        })


async def create_container(session_id: str) -> str:
    docker = await get_docker()
    await ensure_sandbox_network()

    nano_cpus = int(settings.container_cpus * 1e9)
    container = await docker.containers.create({
        "Image": settings.sandbox_image,
        "Cmd": ["sleep", "infinity"],
        "Tty": False,
        "Labels": {"web-terminal": "sandbox", "session-id": session_id},
        "HostConfig": {
            "Memory": _parse_memory(settings.container_memory),
            "NanoCpus": nano_cpus,
            "PidsLimit": settings.container_pids_limit,
            "CapDrop": ["NET_RAW", "SYS_ADMIN", "MKNOD"],
            "NetworkMode": settings.sandbox_network,
            "AutoRemove": False,
        },
    })
    await container.start()
    return container.id


async def create_exec(container_id: str, cols: int = 80, rows: int = 24):
    docker = await get_docker()
    container = await docker.containers.get(container_id)
    exec_inst = await container.exec(
        cmd=["/bin/bash", "--login"],
        stdin=True,
        stdout=True,
        stderr=True,
        tty=True,
        environment=["TERM=xterm-256color", f"COLUMNS={cols}", f"LINES={rows}"],
        workdir="/home/sandbox",
        user="sandbox",
    )
    return exec_inst


async def resize_exec(exec_inst, cols: int, rows: int):
    try:
        await exec_inst.resize(w=cols, h=rows)
    except Exception:
        pass


async def destroy_container(container_id: str):
    if not container_id:
        return
    docker = await get_docker()
    try:
        container = await docker.containers.get(container_id)
        await container.kill()
    except Exception:
        pass
    try:
        container = await docker.containers.get(container_id)
        await container.delete(force=True)
    except Exception:
        pass


async def is_container_running(container_id: str) -> bool:
    if not container_id:
        return False
    docker = await get_docker()
    try:
        container = await docker.containers.get(container_id)
        info = await container.show()
        return info["State"]["Running"]
    except Exception:
        return False


async def list_sandbox_containers() -> list[str]:
    docker = await get_docker()
    try:
        containers = await docker.containers.list(
            filters={"label": ["web-terminal=sandbox"]}
        )
        return [c.id for c in containers]
    except Exception:
        return []


async def inject_ssh_keys(container_id: str, private_key: str):
    """Inject an SSH private key into a running container as the sandbox user.

    Uses base64 encoding to safely transfer key material with arbitrary content.
    NOTE: SSH private keys are stored and transmitted in plaintext within this
    internal tool. Do not expose ssh_private_key in any API response.
    """
    docker = await get_docker()
    container = await docker.containers.get(container_id)

    priv = private_key.strip() if private_key else ""

    def b64(s: str) -> str:
        return base64.b64encode(s.encode()).decode()

    cmds = ["mkdir -p /home/sandbox/.ssh", "chmod 700 /home/sandbox/.ssh"]

    if priv:
        cmds += [
            f"echo '{b64(priv)}' | base64 -d > /home/sandbox/.ssh/id_rsa",
            "chmod 600 /home/sandbox/.ssh/id_rsa",
        ]

    cmds += [
        "printf 'Host *\\n  StrictHostKeyChecking accept-new\\n  IdentitiesOnly yes\\n' "
        "> /home/sandbox/.ssh/config",
        "chmod 600 /home/sandbox/.ssh/config",
        "chown -R sandbox:sandbox /home/sandbox/.ssh",
    ]

    exec_inst = await container.exec(
        cmd=["bash", "-c", " && ".join(cmds)],
        user="root",
        stdout=True,
        stderr=True,
    )
    stream = exec_inst.start(detach=False)
    async with stream:
        while True:
            msg = await stream.read_out()
            if msg is None:
                break


def _parse_memory(mem_str: str) -> int:
    mem_str = mem_str.lower()
    if mem_str.endswith("m"):
        return int(mem_str[:-1]) * 1024 * 1024
    if mem_str.endswith("g"):
        return int(mem_str[:-1]) * 1024 * 1024 * 1024
    return int(mem_str)
