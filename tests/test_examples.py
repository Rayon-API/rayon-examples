import json
from types import SimpleNamespace

import pytest

from examples import southwest_username, starbucks_headers


def test_starbucks_prints_the_requested_headers(monkeypatch, capsys):
    monkeypatch.setenv("RAYON_API_KEY", "test-api-key")
    calls = []

    def solve(url, key):
        calls.append((url, key))
        return SimpleNamespace(headers={"x-example-a": "generated"})

    starbucks_headers.main(solver=solve)
    assert calls == [(starbucks_headers.SOURCE_URL, "test-api-key")]
    assert "generated" in capsys.readouterr().out


def test_southwest_prepares_without_sending_unless_explicit(monkeypatch, capsys):
    monkeypatch.setenv("RAYON_API_KEY", "test-api-key")
    called = []

    def unused(*args, **kwargs):
        called.append(1)

    southwest_username.main([], solver=unused, replay=unused)
    assert not called
    assert "--send" in capsys.readouterr().out


def test_southwest_preserves_required_application_key_and_keeps_rayon_key_out(
    monkeypatch,
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    monkeypatch.setenv("SOUTHWEST_API_KEY", "application-key")
    monkeypatch.setenv("SOUTHWEST_APP_ID", "application-id")
    calls = []

    def solve(url, key):
        assert (url, key) == (southwest_username.SOURCE_URL, "rayon-key")
        return SimpleNamespace(headers={}, cookies=[], profile_used={})

    def replay(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(status_code=204)

    southwest_username.main(
        ["--send", "--username", "dummy_user"], solver=solve, replay=replay
    )
    args, _kwargs = calls[0]
    assert json.loads(args[4]) == {"username": "dummy_user"}
    assert args[5]["x-api-key"] == "application-key"
    assert args[5]["x-app-id"] == "application-id"
    assert "rayon-key" not in str(args[5])


def test_southwest_requires_application_credentials_before_solving(monkeypatch):
    monkeypatch.setenv("RAYON_API_KEY", "test-api-key")
    monkeypatch.delenv("SOUTHWEST_API_KEY", raising=False)

    def unused(*args, **kwargs):
        raise AssertionError("solve must not run")

    with pytest.raises(ValueError, match="SOUTHWEST_API_KEY"):
        southwest_username.main(["--send"], solver=unused)
