import os
from fastapi import FastAPI
from backend.db.database import initDb
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.api import agent, health, sessions, files
from backend.services.agent_manager import agent_manager
from backend.services.cleanup import (
    cleanupStaleStatuses,
    cleanupOrphanedContainers,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database, clean stale states, and handle shutdown."""
    await initDb()
    await cleanupStaleStatuses()
    await cleanupOrphanedContainers()
    yield
    await agent_manager.cleanupAll()


app = FastAPI(title="Computer Use Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(agent.router)
app.include_router(files.router)

frontendDir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontendDir):
    app.mount("/", StaticFiles(directory=frontendDir, html=True), name="frontend")
