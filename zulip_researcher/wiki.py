"""Prepare a wiki repo clone and push a research branch (git over HTTPS + PAT).

The Research agent runs `omp` with cwd inside this clone and edits pages directly; this
module only sets up the branch and ensures it is pushed, so the host can open the PR.
On resume it bases the branch on the existing remote research branch (so the agent sees
and updates the page it already wrote), not on the base branch.
"""

from __future__ import annotations

import os
import subprocess


class WikiError(RuntimeError):
    pass


def _git(args: list[str], cwd: str) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise WikiError(f"git {' '.join(args)} -> {p.stderr.strip()[:300]}")
    return p.stdout.strip()


def _try(args: list[str], cwd: str) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).returncode == 0


def _auth_url(repo_url: str, token: str) -> str:
    if token and repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return repo_url


def prepare(clone_dir: str, repo_url: str, base_branch: str, branch: str,
            token: str, user_name: str, user_email: str, resume: bool = False) -> str:
    """Clone-or-update the wiki, then check out `branch` (from its existing remote head
    on resume, otherwise fresh off `base_branch`)."""
    auth = _auth_url(repo_url, token)
    if not os.path.isdir(os.path.join(clone_dir, ".git")):
        parent = os.path.dirname(clone_dir.rstrip("/")) or "."
        os.makedirs(parent, exist_ok=True)
        _git(["clone", auth, clone_dir], cwd=parent)
    else:
        _git(["remote", "set-url", "origin", auth], cwd=clone_dir)
    _git(["config", "user.name", user_name], cwd=clone_dir)
    _git(["config", "user.email", user_email], cwd=clone_dir)
    if resume and _try(["fetch", "origin", branch], clone_dir):
        _git(["checkout", "-B", branch, f"origin/{branch}"], cwd=clone_dir)
        return clone_dir
    _git(["fetch", "origin", base_branch], cwd=clone_dir)
    _git(["checkout", "-B", base_branch, f"origin/{base_branch}"], cwd=clone_dir)
    _git(["checkout", "-B", branch], cwd=clone_dir)
    return clone_dir


def has_changes(clone_dir: str) -> bool:
    return bool(_git(["status", "--porcelain"], cwd=clone_dir))


def commit_all(clone_dir: str, message: str) -> None:
    _git(["add", "-A"], cwd=clone_dir)
    _git(["commit", "-m", message], cwd=clone_dir)


def push(clone_dir: str, branch: str) -> None:
    _git(["push", "-f", "origin", branch], cwd=clone_dir)
