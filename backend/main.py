import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from services.docker_manager import close_docker
from services.session_manager import cleanup_loop, terminate_all_sessions
from routers import auth, sessions, admin, terminal


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    cleanup_task = asyncio.create_task(cleanup_loop())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await terminate_all_sessions()
    await close_docker()


app = FastAPI(title="Web Terminal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(admin.router)
app.include_router(terminal.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
