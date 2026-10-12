from types import SimpleNamespace

import pytest

from examples.common import replay_once, scoped_cookies

SOURCE = "https://shop.example.com/account"
ENDPOINT = "https://shop.example.com/api/check"


class Session:
    def __init__(self, **options):
        self.options, self.calls = options, []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        return SimpleNamespace(status_code=204)


def result():
    return SimpleNamespace(
        headers={"x-example-" + suffix: "example" for suffix in "abcdfz"},
        cookies=[
            {
                "name": "session",
                "value": "example",
                "domain": ".example.com",
                "path": "/api",
            }
        ],
        profile_used={"navigator": {"userAgent": "Example browser"}},
    )


def test_replay_preserves_body_telemetry_cookie_scope_and_browser_profile():
    sessions = []

    def factory(**kwargs):
        session = Session(**kwargs)
        sessions.append(session)
        return session

    response = replay_once(
        result(),
        SOURCE,
        ENDPOINT,
        "POST",
        '{"username":"dummy"}',
        {"Content-Type": "application/json", "x-api-key": "application-key"},
        session_factory=factory,
    )
    assert response.status_code == 204
    session = sessions[0]
    assert session.options["impersonate"] == "chrome"
    assert session.options["trust_env"] is False
    method, url, request = session.calls[0]
    assert (method, url) == ("POST", ENDPOINT)
    assert request["data"] == '{"username":"dummy"}'
    assert request["allow_redirects"] is False
    assert request["headers"]["x-api-key"] == "application-key"
    assert request["headers"]["User-Agent"] == "Example browser"
    assert not any(name.lower() == "authorization" for name in request["headers"])
    assert all(
        request["headers"][name] == value for name, value in result().headers.items()
    )
    cookie = next(iter(request["cookies"].jar))
    assert (cookie.domain, cookie.path, cookie.secure) == (".example.com", "/api", True)


@pytest.mark.parametrize(
    "target",
    [
        "https://other.example.com/api",
        "http://shop.example.com/api",
        "https://shop.example.com:8443/api",
        "https://user:secret@shop.example.com/api",
    ],
)
def test_replay_rejects_different_or_insecure_origins_before_network(target):
    def unused(**kwargs):
        raise AssertionError("network must not be called")

    with pytest.raises(ValueError):
        replay_once(result(), SOURCE, target, "POST", "{}", {}, session_factory=unused)


def test_cookie_jar_excludes_unrelated_domains_and_preserves_duplicate_paths():
    rows = [
        {"name": "session", "value": "one", "domain": ".example.com", "path": "/"},
        {
            "name": "session",
            "value": "two",
            "domain": "shop.example.com",
            "path": "/api",
        },
        {
            "name": "third_party",
            "value": "private",
            "domain": "other.test",
            "path": "/",
        },
    ]
    cookies = list(scoped_cookies(rows, SOURCE).jar)
    assert len(cookies) == 2
    assert {cookie.value for cookie in cookies} == {"one", "two"}
    assert all(cookie.secure for cookie in cookies)


@pytest.mark.parametrize("navigator", [None, "not-an-object", ["not-an-object"]])
def test_profile_without_navigator_still_uses_top_level_user_agent(navigator):
    value = result()
    value.profile_used = {"navigator": navigator, "user_agent": "Top-level browser"}
    sessions = []

    def factory(**kwargs):
        session = Session(**kwargs)
        sessions.append(session)
        return session

    replay_once(value, SOURCE, ENDPOINT, "POST", "{}", {}, session_factory=factory)
    assert sessions[0].calls[0][2]["headers"]["User-Agent"] == "Top-level browser"


def test_replay_rejects_port_zero_before_network():
    def unused(**kwargs):
        raise AssertionError("network must not be called")

    with pytest.raises(ValueError):
        replay_once(
            result(),
            SOURCE,
            "https://shop.example.com:0/api",
            "POST",
            "{}",
            {},
            session_factory=unused,
        )


def test_replay_explicitly_disables_ambient_proxies(monkeypatch):
    from curl_cffi import CurlOpt

    monkeypatch.delenv("RAYON_REPLAY_PROXY", raising=False)
    sessions = []

    def factory(**kwargs):
        session = Session(**kwargs)
        sessions.append(session)
        return session

    replay_once(result(), SOURCE, ENDPOINT, "POST", "{}", {}, session_factory=factory)
    assert sessions[0].options["curl_options"][CurlOpt.PROXY] == ""
