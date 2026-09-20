"""Configuration.

Same split as the sibling tools:
  - Secrets come from the ENVIRONMENT only.
  - Structure is declared in a TOML file, each key overridable by a RESEARCHER_* env var.
"""

import os
import tomllib
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


# Placeholder values shipped in the example config; treated as "unset" so a
# real run fails early with a clear message instead of acting on nothing.
_PLACEHOLDERS = {
    "https://github.com/you/your-repo.git",
    "https://example.com",
    "andy@example.com",
    "",
}


@dataclass(frozen=True)
class Config:
    # Zulip
    zulip_url: str
    zulip_api_key: str
    zulip_api_username: str
    research_stream: str
    mention_name: str
    operator_email: str
    general_topic: str
    # Preparation interface
    prepare_url: str
    prepare_token: str
    prepare_policy: str
    prepare_format: str
    # Smith Wiki repo (edited via PR)
    wiki_repo_url: str
    wiki_clone_dir: str
    wiki_base_branch: str
    wiki_pages_subdir: str
    wiki_site_url: str
    # Bluesky publishing repos (one per identity)
    bluesky_operator_repo_url: str
    bluesky_agent_repo_url: str
    bluesky_clone_dir: str
    bluesky_posts_subdir: str
    bluesky_branch: str
    # Git identity + auth
    git_user_name: str
    git_user_email: str
    push_token: str
    wiki_push_token: str
    bluesky_operator_push_token: str
    bluesky_agent_push_token: str
    # Behaviour
    poll_interval: int
    wiki_ready_timeout: int
    wiki_ready_interval: int
    dry_run: bool

    def validate_for_publish(self) -> None:
        """Fail fast before a run that mutates Zulip/git/Bluesky.

        Dry-run may proceed with placeholders (it never pushes), but a real run
        needs a preparation endpoint and non-placeholder wiki repo + operator.
        """
        if self.dry_run:
            return
        missing: list[str] = []
        if not self.prepare_url:
            missing.append("PREPARE_URL")
        if not self.prepare_token:
            missing.append("PREPARE_TOKEN")
        if self.wiki_repo_url in _PLACEHOLDERS:
            missing.append("wiki_repo_url (still the example placeholder)")
        if self.operator_email in _PLACEHOLDERS:
            missing.append("operator_email (still the example placeholder)")
        if missing:
            raise ConfigError(
                "cannot run; missing/placeholder configuration: " + ", ".join(missing)
            )


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _load_toml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _req_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ConfigError(f"missing required secret: {name}")
    return v


def _expand(path: str) -> str:
    return os.path.expanduser(path) if path else ""


def _env(name: str, doc: dict, key: str, default: str) -> str:
    return os.environ.get(name, doc.get(key, default))


def load() -> Config:
    doc = _load_toml(os.environ.get("RESEARCHER_CONFIG", "zulip_researcher.toml"))
    push = os.environ.get("PUSH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    return Config(
        zulip_url=_req_env("ZULIP_URL").rstrip("/"),
        zulip_api_key=_req_env("ZULIP_API_KEY"),
        zulip_api_username=os.environ.get("ZULIP_API_USERNAME", "research-bot@example.com"),
        research_stream=_env("RESEARCHER_STREAM", doc, "research_stream", "research"),
        mention_name=_env("RESEARCHER_MENTION_NAME", doc, "mention_name", "research"),
        operator_email=_env("RESEARCHER_OPERATOR_EMAIL", doc, "operator_email", "andy@example.com"),
        general_topic=_env("RESEARCHER_GENERAL_TOPIC", doc, "general_topic", "general"),
        prepare_url=(os.environ.get("PREPARE_URL") or "").rstrip("/"),
        prepare_token=os.environ.get("PREPARE_TOKEN", ""),
        prepare_policy=_env("RESEARCHER_PREPARE_POLICY", doc, "prepare_policy", "faithful-en-v1"),
        prepare_format=_env("RESEARCHER_PREPARE_FORMAT", doc, "prepare_format", "markdown"),
        wiki_repo_url=_env("RESEARCHER_WIKI_REPO_URL", doc, "wiki_repo_url", "https://github.com/you/your-repo.git"),
        wiki_clone_dir=_expand(_env("RESEARCHER_WIKI_CLONE_DIR", doc, "wiki_clone_dir", "~/wiki")),
        wiki_base_branch=_env("RESEARCHER_WIKI_BASE_BRANCH", doc, "wiki_base_branch", "main"),
        wiki_pages_subdir=_env("RESEARCHER_WIKI_PAGES_SUBDIR", doc, "wiki_pages_subdir", "site"),
        wiki_site_url=_env("RESEARCHER_WIKI_SITE_URL", doc, "wiki_site_url", "https://example.com").rstrip("/"),
        bluesky_operator_repo_url=_env("RESEARCHER_BLUESKY_OPERATOR_REPO_URL", doc, "bluesky_operator_repo_url", "https://github.com/you/your-repo.git"),
        bluesky_agent_repo_url=_env("RESEARCHER_BLUESKY_AGENT_REPO_URL", doc, "bluesky_agent_repo_url", "https://github.com/you/your-repo.git"),
        bluesky_clone_dir=_expand(_env("RESEARCHER_BLUESKY_CLONE_DIR", doc, "bluesky_clone_dir", "~/bluesky")),
        bluesky_posts_subdir=_env("RESEARCHER_BLUESKY_POSTS_SUBDIR", doc, "bluesky_posts_subdir", "posts"),
        bluesky_branch=_env("RESEARCHER_BLUESKY_BRANCH", doc, "bluesky_branch", "main"),
        git_user_name=_env("RESEARCHER_GIT_USER_NAME", doc, "git_user_name", "smith.wiki agent"),
        git_user_email=_env("RESEARCHER_GIT_USER_EMAIL", doc, "git_user_email", "agent@smith.wiki"),
        push_token=push,
        wiki_push_token=os.environ.get("WIKI_PUSH_TOKEN") or push,
        bluesky_operator_push_token=os.environ.get("BLUESKY_OPERATOR_PUSH_TOKEN") or push,
        bluesky_agent_push_token=os.environ.get("BLUESKY_AGENT_PUSH_TOKEN") or push,
        poll_interval=int(_env("RESEARCHER_POLL_INTERVAL", doc, "poll_interval", "60")),
        wiki_ready_timeout=int(_env("RESEARCHER_WIKI_READY_TIMEOUT", doc, "wiki_ready_timeout", "600")),
        wiki_ready_interval=int(_env("RESEARCHER_WIKI_READY_INTERVAL", doc, "wiki_ready_interval", "10")),
        dry_run=_flag("RESEARCHER_DRY_RUN"),
    )
