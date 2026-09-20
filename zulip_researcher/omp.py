"""Run the omp agent as a subprocess.

omp reads its prompt from stdin, so the task is piped into omp inside the shell (this
is how the previous system reliably reached the guest). Structured output uses omp's
`--mode=json` NDJSON stream; `assistant_text` extracts the assistant's reply.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import time


class OmpError(RuntimeError):
    pass


def _argv(model: str, json_mode: bool, tools, session: bool, approval: str | None) -> list[str]:
    flags = ["-p", "--no-pty", "--no-title"]
    if json_mode:
        flags.append("--mode=json")
    if tools is False:
        flags.append("--no-tools")
    elif isinstance(tools, str) and tools:
        flags.append("--tools=" + tools)
    if not session:
        flags.append("--no-session")
    if approval:
        flags += ["--approval-mode", approval]
    model_opt = ' --model "$OMP_MODEL"' if model else ""
    cmd = 'printf "%s" "$OMP_TASK" | omp ' + " ".join(flags) + model_opt
    return ["/bin/sh", "-c", cmd]


def run(task: str, *, model: str | None = None, tools: bool = False, session: bool = False,
        json_mode: bool = True, approval: str | None = None, cwd: str | None = None,
        env: dict | None = None, timeout: int = 600) -> str:
    """Run omp once and return its raw stdout."""
    model = model if model is not None else os.environ.get("RESEARCHER_OMP_MODEL", "")
    e = dict(os.environ)
    if env:
        e.update(env)
    e["OMP_TASK"] = task
    if model:
        e["OMP_MODEL"] = model
    proc = subprocess.run(
        _argv(model, json_mode, tools, session, approval),
        cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise OmpError(f"omp exit {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout

def run_stream(task: str, *, model: str | None = None, tools=False, session: bool = False,
               json_mode: bool = True, approval: str | None = None, cwd: str | None = None,
               env: dict | None = None, timeout: int = 600, on_tool=None) -> str:
    """Run omp streaming its --mode=json NDJSON. For each tool the agent starts, call
    on_tool(tool_name, intent, args). Returns the full raw stdout. Reads with a select()
    deadline so a stalled model (no output) still honours `timeout`."""
    model = model if model is not None else os.environ.get("RESEARCHER_OMP_MODEL", "")
    e = dict(os.environ)
    if env:
        e.update(env)
    e["OMP_TASK"] = task
    if model:
        e["OMP_MODEL"] = model
    proc = subprocess.Popen(_argv(model, json_mode, tools, session, approval),
                            cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    buf = b""

    def _feed(line: bytes) -> None:
        if on_tool is None or b"tool_execution_start" not in line:
            return
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if ev.get("type") == "tool_execution_start":
            try:
                on_tool(ev.get("toolName") or "", ev.get("intent") or "", ev.get("args") or {})
            except Exception:
                pass

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                raise OmpError(f"omp timed out after {timeout} seconds")
            r, _, _ = select.select([proc.stdout], [], [], min(remaining, 5.0))
            if proc.stdout in r:
                data = os.read(proc.stdout.fileno(), 65536)
                if not data:
                    break
                chunks.append(data)
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    _feed(line)
            elif proc.poll() is not None:
                break
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
    proc.wait()
    err = (proc.stderr.read().decode(errors="replace")[:500] if proc.stderr else "")
    if proc.returncode not in (0, None):
        raise OmpError(f"omp exit {proc.returncode}: {err}")
    return b"".join(chunks).decode(errors="replace")


def assistant_text(stdout: str) -> str:
    """Extract the assistant's text from omp's --mode=json NDJSON stream."""
    parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "message_end":
            msg = ev.get("message") or {}
            if msg.get("role") == "assistant":
                for c in msg.get("content") or []:
                    if c.get("type") == "text" and c.get("text"):
                        parts.append(c["text"])
    return "\n".join(parts).strip()


def ask(task: str, *, model: str | None = None) -> str:
    """Convenience: run omp (json, no tools, no session) and return the reply text."""
    return assistant_text(run(task, model=model))
