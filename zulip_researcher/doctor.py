"""Preflight: verify creds are present and external systems reachable, mutating nothing.

`doctor` is read-only. It reports which secrets are set, whether Zulip and the
preparation interface answer, whether the repos clone, and whether omp is on PATH — so
the operator can confirm the setup before running the listener. Run it on the host with
`nix run .#debug -- doctor`, or in the VM with `nix run .#sandbox -- doctor`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from . import config, prepare as prepare_mod, wiki, zulip

REQUIRED_SECRETS = ["ZULIP_URL", "ZULIP_API_KEY", "PREPARE_URL", "PREPARE_TOKEN"]
OPTIONAL_SECRETS = [
    "PUSH_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "WEB_SEARCH_API_KEY",
    "BLUESKY_OPERATOR_APP_PASSWORD", "BLUESKY_AGENT_APP_PASSWORD",
]

_PLACEHOLDERS = {
    "https://github.com/you/your-repo.git",
    "https://github.com/you/your-wiki.git",
    "https://github.com/you/your-bluesky-operator.git",
    "https://github.com/you/your-bluesky-agent.git",
    "",
}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def check_secrets(env: dict | None = None) -> list[Check]:
    env = env if env is not None else os.environ
    checks: list[Check] = []
    for n in REQUIRED_SECRETS:
        present = bool(env.get(n))
        checks.append(Check(f"secret {n}", present, "present" if present else "MISSING (required)"))
    for n in OPTIONAL_SECRETS:
        present = bool(env.get(n))
        checks.append(Check(f"secret {n}", True, "present" if present else "absent (optional)"))
    return checks


def check_omp(which=shutil.which) -> Check:
    found = bool(which("omp"))
    return Check("omp on PATH", found, "" if found else "omp not found")


def check_zulip(cfg, zc=None) -> Check:
    try:
        zc = zc or zulip.Zulip(cfg.zulip_url, cfg.zulip_api_key, cfg.zulip_api_username)
        sid = zc.get_stream_id(cfg.research_stream)
        return Check(f"zulip #{cfg.research_stream}", True, f"stream_id={sid}")
    except Exception as e:  # noqa: BLE001 - report any failure verbatim
        return Check("zulip", False, str(e)[:200])


def check_prepare(cfg, client=None) -> Check:
    try:
        client = client or prepare_mod.PreparationClient(cfg.prepare_url, cfg.prepare_token)
        client.prepare("ping", policy=cfg.prepare_policy, fmt=cfg.prepare_format)
        return Check("prepare interface", True, "reachable")
    except Exception as e:  # noqa: BLE001
        return Check("prepare interface", False, str(e)[:200])


def _clone(url: str, token: str) -> None:
    auth = wiki._auth_url(url, token)
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run(["git", "clone", "--depth", "1", auth, f"{d}/r"],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip()[:200])


def check_clone(label: str, url: str, token: str, runner=_clone) -> Check:
    if url in _PLACEHOLDERS:
        return Check(f"clone {label}", True, "skipped (placeholder)")
    try:
        runner(url, token)
        return Check(f"clone {label}", True, "ok")
    except Exception as e:  # noqa: BLE001
        return Check(f"clone {label}", False, str(e)[:200])


def run() -> int:
    checks = check_secrets()
    checks.append(check_omp())
    try:
        cfg = config.load()
    except config.ConfigError as e:
        checks.append(Check("config", False, str(e)[:200]))
        cfg = None
    if cfg is not None:
        checks.append(check_zulip(cfg))
        checks.append(check_prepare(cfg))
        checks.append(check_clone("wiki", cfg.wiki_repo_url, cfg.push_token))
        checks.append(check_clone("bluesky-operator", cfg.bluesky_operator_repo_url, cfg.push_token))
        checks.append(check_clone("bluesky-agent", cfg.bluesky_agent_repo_url, cfg.push_token))

    ok_all = True
    for c in checks:
        print(f"{'✓' if c.ok else '✗'} {c.name}" + (f" — {c.detail}" if c.detail else ""))
        ok_all = ok_all and c.ok
    print("\nOK" if ok_all else "\nFAILED — fix the ✗ above")
    return 0 if ok_all else 1
