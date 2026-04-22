### Author: Nadir Zane

# Computer Using Agent

A Docker-based computer-use agent powered by Anthropic's Claude. Each session dynamically spawns an isolated X11 desktop with real-time SSE streaming, browser-based VNC, file management, and audio support. Sessions run fully concurrently — no fixed display limits, no queuing, no blocking.

## Demo Video

Attached with the email

## Architecture

The system runs inside a single Docker container. When a user submits a task, **AgentManager** spawns an independent **AgentWorker** (as an `asyncio.Task`) and **DisplayManager** allocates a fresh X11 display — there is no fixed limit and no queuing.

Each session gets its own **Xvfb + mutter + tint2 + x11vnc** stack on a dynamically assigned display number (`:1`, `:2`, `:N`). A single **websockify** proxy on port 6080 routes each browser to the correct VNC backend using `?token=<session_id>`.

**UserManager** creates an isolated Linux user per session with restricted sudo. **SSE streaming** pushes every tool call, text chunk, screenshot, and status change to the frontend in real time — no polling.

```
Browser ──► FastAPI :8000 ──► AgentManager ──┬── AgentWorker 1 ──► SamplingLoop ──► Claude API
         │                                   ├── AgentWorker 2 ──► SamplingLoop ──► Claude API
         │                                   ├── AgentWorker N ──► ...
         │                                   ├── DisplayManager (dynamic Xvfb/VNC per session)
         │                                   ├── UserManager (isolated Linux users)
         │                                   └── SQLite (session + message persistence)
         │
         └─► Websockify :6080 ──► token routing ──┬── x11vnc :5901 (Session 1)
                                                   ├── x11vnc :5902 (Session 2)
                                                   └── x11vnc :5900+N (Session N)
```

## Quick Start

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/), Docker Compose, and an [Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/muhammad65muneeb-create/COMPUTER-USING-AGENT.git
cd computer-using-agent
cp .env.example .env       # set ANTHROPIC_API_KEY
docker compose up --build
```

Open [localhost:8000](http://localhost:8000). API docs at [localhost:8000/docs](http://localhost:8000/docs).

## Project Structure

```
backend/          FastAPI server, Claude integration, session management
  api/            REST endpoints (sessions, agent, files, health)
  db/             SQLAlchemy models, schemas, async engine
  services/       AgentManager, AgentWorker, DisplayManager, UserManager, SamplingLoop
  tools/          Bash, Computer (screenshot/mouse/keyboard), Edit
frontend/         Browser UI (vanilla JS, ES modules)
  modules/        State, sessions, chat/SSE, VNC, files, dialogs, audio
image/            Docker entrypoint and X11/VNC/audio startup scripts
```

## Environment Variables

| Variable           | Default                                       | Description                |
|--------------------|-----------------------------------------------|----------------------------|
| `ANTHROPIC_API_KEY`| —                                             | **Required.** API key      |
| `DATABASE_URL`     | `sqlite+aiosqlite:///./sessiondb/sessions.db` | SQLAlchemy database URL    |
| `WIDTH`            | `1024`                                        | Display width (px)         |
| `HEIGHT`           | `768`                                         | Display height (px)        |

## Ports

| Port | Service                            |
|------|------------------------------------|
| 8000 | FastAPI (API + frontend)           |
| 6080 | noVNC (token-based VNC routing)    |
| 4680 | WebSocket audio (PulseAudio)       |

## Local Development

Requires Python 3.11+ and system packages (`xvfb`, `x11vnc`, `scrot`, `xdotool`, `mutter`, `tint2`).

```bash
./setup.sh
source .venv/bin/activate
cp .env.example .env
uvicorn backend.main:app --reload --port 8000
```
