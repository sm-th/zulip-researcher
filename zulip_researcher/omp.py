"""Run the omp agent as a subprocess.

omp reads its prompt from stdin, so the task is piped into omp inside the shell (this
is how the previous system reliably reached the guest). Structured output uses omp's
`--mode=json` NDJSON stream; `assistant_text` extracts the assistant's reply.
"""

from __future__ import annotations

import json
import os
import subprocess


class OmpError(RuntimeError):
    pass


def _argv(model: str, json_mode: bool, tools: bool, session: bool, approval: str | None) -> list[str]:
    flags = ["-p", "--no-pty", "--no-title"]
    if json_mode:
        flags.append("--mode=json")
    if not tools:
        flags.append("--no-tools")
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
