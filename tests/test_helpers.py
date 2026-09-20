"""Unit tests for the small helper modules."""

from zulip_researcher.github import repo_slug
from zulip_researcher.slug import slug
from zulip_researcher.wiki import _auth_url


def test_slug_matches_eleventy_rules():
    assert slug("Do rebuilds dominate?") == "do-rebuilds-dominate"
    assert slug("  A/B & C  ") == "a-b-c"


def test_repo_slug_parses_https_and_ssh():
    assert repo_slug("https://github.com/owner/name.git") == "owner/name"
    assert repo_slug("git@github.com:owner/name.git") == "owner/name"


def test_auth_url_injects_token_only_for_https():
    assert _auth_url("https://github.com/o/n.git", "tok") == \
        "https://x-access-token:tok@github.com/o/n.git"
    assert _auth_url("https://github.com/o/n.git", "") == "https://github.com/o/n.git"
    assert _auth_url("git@github.com:o/n.git", "tok") == "git@github.com:o/n.git"
