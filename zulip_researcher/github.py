"""Open a pull request via the GitHub REST API (token auth)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class GitHubError(RuntimeError):
    pass


def repo_slug(repo_url: str) -> str:
    """`https://github.com/owner/name.git` (or ssh form) -> `owner/name`."""
    m = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise GitHubError(f"cannot parse owner/name from {repo_url!r}")
    return m.group(1)


def open_pr(repo: str, *, token: str, head: str, base: str, title: str, body: str) -> str:
    """Open a PR and return its html_url. `repo` is `owner/name`."""
    url = f"https://api.github.com/repos/{repo}/pulls"
    data = json.dumps({"title": title, "head": head, "base": base, "body": body}).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "zulip-researcher/0.1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise GitHubError(f"open_pr -> HTTP {e.code}: {detail}") from None
    return doc.get("html_url", "")


def pr_number(html_url: str) -> int | None:
    """`https://github.com/owner/name/pull/42` -> `42`."""
    m = re.search(r"/pull/(\d+)/?$", html_url or "")
    return int(m.group(1)) if m else None


def merge_pr(repo: str, number: int, *, token: str, method: str = "squash") -> None:
    """Merge PR `number` in `repo` (squash by default). `repo` is `owner/name`."""
    url = f"https://api.github.com/repos/{repo}/pulls/{number}/merge"
    data = json.dumps({"merge_method": method}).encode()
    req = urllib.request.Request(
        url, data=data, method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "zulip-researcher/0.1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise GitHubError(f"merge_pr -> HTTP {e.code}: {detail}") from None
