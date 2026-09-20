"""Tests for the doctor preflight check logic."""

from zulip_researcher.doctor import check_clone, check_secrets


def _by_name(checks):
    return {c.name: c for c in checks}


def test_required_secret_missing_fails():
    checks = _by_name(check_secrets(env={"ZULIP_URL": "x", "ZULIP_API_KEY": "y"}))
    assert checks["secret ZULIP_URL"].ok
    assert not checks["secret PREPARE_URL"].ok
    assert "MISSING" in checks["secret PREPARE_URL"].detail


def test_optional_secret_absent_is_ok():
    checks = _by_name(check_secrets(env={}))
    assert checks["secret PUSH_TOKEN"].ok               # optional -> ok even if absent
    assert "absent" in checks["secret PUSH_TOKEN"].detail


def test_clone_skips_placeholder_without_running():
    ran = []
    c = check_clone("wiki", "https://github.com/you/your-wiki.git", "",
                    runner=lambda url, token: ran.append(url))
    assert c.ok and "placeholder" in c.detail
    assert ran == []                                    # placeholder never clones


def test_clone_reports_runner_failure():
    def boom(url, token):
        raise RuntimeError("auth failed")
    c = check_clone("wiki", "https://github.com/real/repo.git", "tok", runner=boom)
    assert not c.ok and "auth failed" in c.detail
