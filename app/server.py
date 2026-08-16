"""Crop evaluation workspace — local dashboard server.

Run:  python app/server.py        (then open http://127.0.0.1:8000)

Cards are pushed onto the page by app/push.py and stream to the browser over SSE,
so the dashboard updates while you are asking questions in another window.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import agent
import analytics

STATIC = Path(__file__).resolve().parent / "static"

PORT = int(os.environ.get("PORT", "8000"))

# Shut down after this many minutes with no browser attached, so closing the tab
# doesn't leave a server running forever. Set IDLE_EXIT_MIN=0 to disable.
IDLE_EXIT_MIN = float(os.environ.get("IDLE_EXIT_MIN", "30"))

SERVER: list = []              # the uvicorn Server, so the watchdog can stop it
_last_active = [time.time()]


async def _idle_watchdog() -> None:
    while IDLE_EXIT_MIN > 0:
        await asyncio.sleep(15)
        idle_for = time.time() - _last_active[0]
        if SUBSCRIBERS or _busy.locked():
            _last_active[0] = time.time()
            continue
        if idle_for > IDLE_EXIT_MIN * 60:
            print(f"no browser for {IDLE_EXIT_MIN:g} min — shutting down")
            AGENT.cancel()
            if SERVER:
                SERVER[0].should_exit = True
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_idle_watchdog())
    try:
        yield
    finally:
        task.cancel()
        AGENT.cancel()         # never leave a headless claude running
        _save()


app = FastAPI(title="Crop Evaluation Workspace", lifespan=lifespan)

# The server binds to loopback, but defend in depth anyway.
LOCAL = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}

# Host header allowlist. Without this, a site you visit could point its own domain
# at 127.0.0.1 (DNS rebinding) and reach this API from your browser as same-origin,
# where CORS no longer protects you. The client IP would still be loopback, so the
# check below is what actually stops it.
ALLOWED_HOSTS = {f"{h}:{PORT}" for h in ("127.0.0.1", "localhost", "[::1]")} | \
                {"127.0.0.1", "localhost", "[::1]"}


@app.middleware("http")
async def local_only(request: Request, call_next):
    _last_active[0] = time.time()
    client = request.client.host if request.client else None
    if client not in LOCAL:
        return JSONResponse({"detail": "local connections only"}, status_code=403)
    host = (request.headers.get("host") or "").lower()
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "unrecognised Host header"}, status_code=403)
    return await call_next(request)

STATE = Path(__file__).resolve().parent / ".state.json"

CARDS: list[dict] = []
CHAT: list[dict] = []
SUBSCRIBERS: list[asyncio.Queue] = []
_next_id = [1]
_next_msg = [1]


_saved_agent: dict = {}


def _save() -> None:
    """Persist the board so a server restart doesn't wipe it."""
    ag = globals().get("AGENT")
    try:
        STATE.write_text(json.dumps(
            {"cards": CARDS, "chat": CHAT,
             "next_id": _next_id[0], "next_msg": _next_msg[0],
             "agent": {"session_id": ag.session_id, "started": ag.started} if ag else {}}),
            encoding="utf8")
    except OSError:
        pass


def _load() -> None:
    if not STATE.exists():
        return
    try:
        s = json.loads(STATE.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return
    CARDS.extend(s.get("cards", []))
    CHAT.extend(s.get("chat", []))
    _next_id[0] = s.get("next_id", len(CARDS) + 1)
    _next_msg[0] = s.get("next_msg", len(CHAT) + 1)
    _saved_agent.update(s.get("agent") or {})


_load()


def _broadcast(event: str, payload: dict) -> None:
    msg = {"event": event, "data": payload}
    for q in list(SUBSCRIBERS):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass


class Card(BaseModel):
    type: str                 # table | bar | scatter | histogram | heatmap | tree | note
    title: str = ""
    subtitle: str = ""
    data: dict = {}
    sql: str = ""
    width: str = "half"       # half | full


class Query(BaseModel):
    sql: str
    dataset: str | None = None


class Message(BaseModel):
    role: str                 # user | assistant | tool
    text: str
    ts: str = ""


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/schema")
def get_schema(dataset: str | None = None):
    try:
        return analytics.schema(dataset)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/cards")
def get_cards():
    return CARDS


@app.post("/api/cards")
def add_card(card: Card):
    c = card.model_dump()
    c["id"] = _next_id[0]
    c["created"] = time.time()
    _next_id[0] += 1
    CARDS.append(c)
    _save()
    _broadcast("card", c)
    return {"ok": True, "id": c["id"]}


@app.delete("/api/cards")
def clear_cards():
    CARDS.clear()
    _save()
    _broadcast("clear", {})
    return {"ok": True}


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: int):
    global CARDS
    CARDS = [c for c in CARDS if c["id"] != card_id]
    _save()
    _broadcast("delete", {"id": card_id})
    return {"ok": True}


@app.get("/api/chat")
def get_chat():
    return CHAT


@app.post("/api/chat")
def add_message(m: Message):
    msg = m.model_dump()
    msg["id"] = _next_msg[0]
    _next_msg[0] += 1
    # A streamed assistant turn arrives in fragments; merge consecutive same-role text.
    if CHAT and CHAT[-1]["role"] == msg["role"] == "assistant":
        CHAT[-1]["text"] += "\n" + msg["text"]
        _save()
        _broadcast("chat_update", CHAT[-1])
        return {"ok": True, "id": CHAT[-1]["id"], "merged": True}
    CHAT.append(msg)
    _save()
    _broadcast("chat", msg)
    return {"ok": True, "id": msg["id"]}


@app.delete("/api/chat")
def clear_chat():
    """Clear the visible transcript only — the agent still remembers. Use /api/reset
    to start a genuinely new conversation."""
    CHAT.clear()
    _save()
    _broadcast("chat_clear", {})
    return {"ok": True}


class Ask(BaseModel):
    prompt: str


# Reuse the previous session id so a server restart continues the same conversation
# rather than silently starting a fresh one.
AGENT = agent.Session(_saved_agent.get("session_id"))
AGENT.started = bool(_saved_agent.get("started"))
_busy = threading.Lock()


def _emit(role: str, text: str) -> None:
    """Append to the chat panel and push it to the browser."""
    add_message(Message(role=role, text=text))


def _run_agent(prompt: str) -> None:
    try:
        for ev in AGENT.ask(prompt):
            kind = ev.get("kind")
            if kind == "text":
                _emit("assistant", ev["text"])
            elif kind == "tool":
                _emit("tool", ev["text"])
            elif kind == "error":
                _emit("error", ev["text"])
            elif kind == "done":
                _broadcast("agent_done", {})
    except Exception as e:                      # never leave the UI spinning
        _emit("error", f"agent failed: {e}")
        _broadcast("agent_done", {})
    finally:
        if _busy.locked():
            _busy.release()


@app.get("/api/agent")
def agent_status():
    return {"available": bool(agent.available()), "busy": _busy.locked()}


@app.post("/api/ask")
def ask(a: Ask):
    prompt = a.prompt.strip()
    if not prompt:
        raise HTTPException(400, "empty prompt")
    if not agent.available():
        raise HTTPException(503, "Claude Code not found on PATH")
    if not _busy.acquire(blocking=False):
        raise HTTPException(409, "still answering the previous question")
    _emit("user", prompt)
    _save()                      # remember the session id even if the turn crashes
    _broadcast("agent_busy", {})
    threading.Thread(target=_run_agent, args=(prompt,), daemon=True).start()
    return {"ok": True}


@app.post("/api/cancel")
def cancel():
    AGENT.cancel()
    return {"ok": True}


@app.post("/api/reset")
def reset_conversation():
    """Start a new conversation: clear the transcript AND give the agent a fresh
    session, so it genuinely forgets rather than just hiding the history."""
    global AGENT
    AGENT.cancel()
    AGENT = agent.Session()          # new session id => no --resume => no memory
    CHAT.clear()
    _save()
    _broadcast("chat_clear", {})
    return {"ok": True, "session": AGENT.session_id}


@app.post("/api/query")
def query(q: Query):
    try:
        return analytics.run_sql(q.sql, q.dataset)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/stream")
async def stream():
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    SUBSCRIBERS.append(q)
    _last_active[0] = time.time()

    async def gen():
        try:
            yield f"event: ping\ndata: {json.dumps({'cards': len(CARDS)})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
        finally:
            if q in SUBSCRIBERS:
                SUBSCRIBERS.remove(q)
            _last_active[0] = time.time()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import uvicorn
    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    srv = uvicorn.Server(cfg)
    SERVER.append(srv)
    print(f"http://127.0.0.1:{PORT}   (ctrl-c to stop"
          + (f"; auto-stops after {IDLE_EXIT_MIN:g} min with no browser)" if IDLE_EXIT_MIN > 0 else ")"))
    srv.run()
