"""Drive a local Claude Code process from the dashboard.

Runs `claude -p` in headless streaming mode against the project directory and
yields sanitised events. Nothing here talks to Anthropic directly — it shells out
to the Claude Code you already have installed and signed in, so no API key or
credential is ever read, stored, or transmitted by this app.

Privacy: raw stream events carry absolute paths, the MCP server list and other
machine detail. Only text and tool names leave this module, and everything is run
through `redact()` first so a home directory can't end up on screen or in
.state.json.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Callable, Iterator

ROOT = Path(__file__).resolve().parent.parent

# --allowedTools is an auto-approve list, not a restriction: in headless mode there
# is nobody to prompt, so anything not denied simply runs. --disallowedTools is the
# control that is actually enforced (a denied tool is removed from the session).
#
# The agent therefore runs with the same file and shell access you have when you
# type into Claude Code yourself — this is NOT a sandbox. What the deny list buys
# is that it cannot modify files or reach the network, so a bad answer stays a bad
# answer instead of becoming a bad edit or an outbound request.
ALLOWED_TOOLS = [
    "Read", "Grep", "Glob",
    "Bash(python app/push.py:*)",
]

DENIED_TOOLS = [
    "Write", "Edit", "NotebookEdit",        # no file modification
    "WebFetch", "WebSearch",                # no outbound network
    "Task", "SendMessage",                  # no subagents / messaging
    "CronCreate", "CronDelete", "RemoteTrigger", "PushNotification",
]

SYSTEM_PROMPT = """\
You are answering questions inside a local crop-evaluation dashboard.

To look something up WITHOUT putting anything on the board — checking a number,
exploring, answering a question that doesn't need a chart:

  python app/push.py query "<SELECT ...>"

The user sees a web page with a card board. To show them something, push a card:

  python app/push.py sql "<SELECT ...>" --as table|bar|scatter --title "..."
  python app/push.py dist <table> <column> [--group-by <col>] --title "..."
  python app/push.py corr <table> <col1,col2,...> --title "..."
  python app/push.py pca [--markers N]
  python app/push.py tree [--n N]
  python app/push.py note "**text**" --width full

Scatter takes --x --y --label --group naming result columns. Every card accepts
--title, --subtitle and --width half|full.

Read data/<dataset>/semantics.md first when a question depends on what a column
means, what its units are, or which direction a score runs — it records the
scoring scales and known data quirks.

Read methods/analysis-guide.md BEFORE any quantitative analysis — always for
anything involving relatedness, trees, clustering, genetic distance, diversity,
population structure, correlation, or significance.

  Part 1  six-step workflow that always applies
  Part 2  method deep dives, consult as needed
  Part 3  what THIS codebase does — the defaults subsample and thin, so they are
          wrong for most questions; override them as it says
  Part 4  claim discipline: never present fitted or imputed values as observations
  Part 5  checklist to run before pushing any analytical card

Follow it over your own defaults. State the sample actually analysed — individuals,
markers, method, exclusions — in the card subtitle. Where the tooling cannot do the
correct thing, say so plainly instead of simulating it.

Prefer showing over telling: push a card, then give a short written answer about
what it shows. Keep replies to a few sentences; the card carries the detail. If the
user says they don't want a card, use `query` and just answer — don't push one anyway.
"""

_HOME = str(Path.home())
_USER = os.environ.get("USERNAME") or os.environ.get("USER") or ""
_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*")


def redact(text: str) -> str:
    """Strip anything that identifies this machine."""
    if not text:
        return text
    out = text.replace(_HOME, "~").replace(_HOME.replace("\\", "/"), "~")
    if _USER:
        out = re.sub(re.escape(_USER), "<user>", out, flags=re.I)
    # any remaining absolute Windows path -> keep only the tail
    out = _PATH_RE.sub(lambda m: ".../" + m.group(0).replace("\\", "/").rsplit("/", 1)[-1], out)
    return out


def available() -> str | None:
    return shutil.which("claude")


class Session:
    """One conversation, resumed across turns via a stable session id."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.started = False
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()

    def ask(self, prompt: str, model: str | None = None) -> Iterator[dict]:
        """Run one turn, yielding {kind, ...} events."""
        exe = available()
        if not exe:
            yield {"kind": "error", "text":
                   "Claude Code is not installed, or `claude` is not on PATH. "
                   "Install it and sign in, then restart the server."}
            return

        cmd = [exe, "-p", prompt,
               "--output-format", "stream-json", "--verbose",
               "--allowedTools", *ALLOWED_TOOLS,
               "--disallowedTools", *DENIED_TOOLS,
               "--append-system-prompt", SYSTEM_PROMPT]
        cmd += ["--resume", self.session_id] if self.started else \
               ["--session-id", self.session_id]
        if model:
            cmd += ["--model", model]

        try:
            proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            yield {"kind": "error", "text": f"could not start Claude Code: {e}"}
            return

        with self._lock:
            self._proc = proc
        self.started = True

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield from self._translate(ev)
        finally:
            proc.stdout.close()
            err = proc.stderr.read()
            proc.stderr.close()
            code = proc.wait()
            with self._lock:
                self._proc = None
            if code not in (0, None) and err.strip():
                yield {"kind": "error", "text": redact(err.strip()[:400])}

    @staticmethod
    def _translate(ev: dict) -> Iterator[dict]:
        """Raw stream event -> sanitised dashboard event. Drops everything else."""
        t = ev.get("type")
        if t == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    yield {"kind": "text", "text": redact(b["text"])}
                elif b.get("type") == "tool_use":
                    yield {"kind": "tool", "text": redact(_tool_label(b))}
        elif t == "result":
            yield {"kind": "done",
                   "error": bool(ev.get("is_error")),
                   "turns": ev.get("num_turns", 0)}
        # system/init, rate_limit_event, user/tool_result: deliberately dropped —
        # they carry cwd, MCP servers, memory paths and tool output.


def _tool_label(block: dict) -> str:
    name = block.get("name", "tool")
    inp = block.get("input") or {}
    if name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command", ""))[:110]
        return f"{name}: {cmd}"
    if name in ("Read", "Grep", "Glob"):
        arg = inp.get("file_path") or inp.get("pattern") or ""
        return f"{name}: {str(arg)[:80]}"
    return name


def run(prompt: str, session: Session, on_event: Callable[[dict], None]) -> None:
    for ev in session.ask(prompt):
        on_event(ev)
