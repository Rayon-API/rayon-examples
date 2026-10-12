import json

import pytest
from curl_cffi import CurlOpt

from examples import common

SOURCE = "https://shop.example.com/account"
ENDPOINT = "https://shop.example.com/api/check"
PROFILE = {"user_agent": "Owned Chrome browser"}
REQUEST = {
    "url": ENDPOINT,
    "method": "POST",
    "content_type": "application/json",
    "body": ' {"x":"é"}\n',
}


def run(transport, **changes):
    kwargs = dict(
        source_url=SOURCE,
        script_urls=["https://cdn.example/selected.js"],
        profile=PROFILE,
        request=REQUEST,
        application_headers={"x-api-key": "app-key"},
        send=True,
        client_factory=transport["client_factory"],
        session_factory=transport["session_factory"],
    )
    kwargs.update(changes)
    return common.generate_material(**kwargs)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-secret")
    monkeypatch.delenv("RAYON_TARGET_PROXY", raising=False)


def test_explicit_proxy_and_persistent_session_are_shared_for_every_target_request(
    monkeypatch, transport
):
    monkeypatch.setenv("HTTPS_PROXY", "http://ambient.example")
    monkeypatch.setenv("RAYON_TARGET_PROXY", "http://sticky.example:8080")
    run(transport)
    assert len(transport["sessions"]) == 1
    session = transport["sessions"][0]
    assert session.options["proxy"] == "http://sticky.example:8080"
    assert session.options["trust_env"] is False
    assert session.options["impersonate"] == "chrome"
    assert session.options["default_headers"] is False
    assert transport["events"] == [
        ("GET", SOURCE),
        ("GET", "https://cdn.example/selected.js"),
        ("generate", None),
        ("POST", ENDPOINT),
    ]
    assert transport["shapes"][0]["request"]["body"] == REQUEST["body"]
    assert session.calls[-1][2]["data"] == REQUEST["body"].encode()


def test_no_ambient_proxy_without_explicit_setting(monkeypatch, transport):
    monkeypatch.setenv("ALL_PROXY", "http://ambient.example")
    run(transport)
    assert transport["sessions"][0].options["curl_options"][CurlOpt.PROXY] == ""
    assert transport["sessions"][0].options["proxy"] is None


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example/api",
        "http://shop.example.com/api",
        "https://shop.example.com:8443/api",
        "https://user:secret@shop.example.com/api",
        "https://shop.example.com:0/api",
        "https://shop.example.com/api#fragment",
        "https://shop.example.com/api\n",
        "https://shop.example.com\\evil/api",
    ],
)
def test_exact_https_origin_rejected_before_network(transport, url):
    with pytest.raises(ValueError):
        run(transport, request={**REQUEST, "url": url})
    assert not transport["sessions"] and not transport["clients"]


@pytest.mark.parametrize(
    "scripts",
    [
        [],
        ["http://cdn.example/a.js"],
        ["https://user:key@cdn.example/a.js"],
        ["https://cdn.example/a.js"] * 17,
    ],
)
def test_explicit_full_https_scripts_required_before_network(transport, scripts):
    with pytest.raises(ValueError):
        run(transport, script_urls=scripts)
    assert not transport["sessions"]


@pytest.mark.parametrize("status", [301, 302, 307, 308, 404, 500])
def test_material_errors_and_redirects_stop_generation_and_close_session(
    transport, status
):
    transport["status"] = status
    with pytest.raises(ValueError):
        run(transport)
    assert not transport["shapes"]
    assert transport["sessions"][0].closed


@pytest.mark.parametrize("fault", ["target_error", "api_error"])
def test_failure_closes_session_and_api_client_if_created(transport, fault):
    transport[fault] = True
    with pytest.raises(RuntimeError):
        run(transport)
    assert transport["sessions"][0].closed
    assert all(client.closed for client in transport["clients"])


@pytest.mark.parametrize(
    "profile",
    [
        {},
        {"unknown": 1},
        {"user_agent": "one", "navigator": {"userAgent": "two"}},
        {"user_agent": "bad\nUA"},
        {"user_agent": "UA", "screen": {"width": True}},
    ],
)
def test_invalid_or_missing_user_owned_profile_before_network(transport, profile):
    with pytest.raises(ValueError):
        run(transport, profile=profile)
    assert not transport["sessions"]


def test_profile_read_preserves_user_input_and_rejects_nonstandard_json(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(PROFILE))
    assert common.load_profile(path) == PROFILE
    for raw in [
        '{"user_agent":"one","user_agent":"two"}',
        '{"window":{"devicePixelRatio":NaN}}',
        "[]",
    ]:
        path.write_text(raw)
        with pytest.raises(ValueError):
            common.load_profile(path)


def test_no_application_post_without_explicit_send(transport):
    result, response = run(transport, send=False)
    assert result.headers and response is None
    assert all(call[0] == "GET" for call in transport["sessions"][0].calls)


def test_different_returned_user_agent_stops_application_post(transport):
    transport["profile_used"] = {"user_agent": "Different browser"}
    with pytest.raises(ValueError, match="profile"):
        run(transport)
    assert all(call[0] == "GET" for call in transport["sessions"][0].calls)
    assert transport["sessions"][0].closed


def test_generated_headers_cannot_replace_application_credentials(transport):
    transport["headers"] = {"X-API-KEY": "wrong"}
    with pytest.raises(ValueError, match="header"):
        run(transport)
    assert all(call[0] == "GET" for call in transport["sessions"][0].calls)


def test_target_cookie_jar_keeps_host_path_secure_and_httponly_scoping():
    from http.cookiejar import Cookie
    from urllib.request import Request
    from curl_cffi.requests import Cookies

    cookies = Cookies()
    for name, domain, host_only, path, secure, extra in [
        ("host_only", "shop.example.com", True, "/", True, {"HttpOnly": None}),
        ("path_scoped", ".example.com", False, "/api", True, {}),
        ("other", "unrelated.example", True, "/", True, {}),
    ]:
        cookies.jar.set_cookie(
            Cookie(
                0,
                name,
                "value",
                None,
                False,
                domain,
                not host_only,
                domain.startswith("."),
                path,
                True,
                secure,
                None,
                True,
                None,
                None,
                extra,
                False,
            )
        )
    # The persistent jar retains metadata; curl enforces its destination scope.
    request = Request("https://unrelated.example/api/check")
    cookies.jar.add_cookie_header(request)
    assert request.get_header("Cookie") == "other=value"
    cookie = next(cookie for cookie in cookies.jar if cookie.name == "host_only")
    assert cookie.has_nonstandard_attr("HttpOnly") and not cookie.domain_specified
    request = Request("https://shop.example.com/account")
    cookies.jar.add_cookie_header(request)
    assert "path_scoped" not in request.get_header("Cookie", "")
    insecure = Request("http://shop.example.com/api/check")
    cookies.jar.add_cookie_header(insecure)
    assert insecure.get_header("Cookie") is None


def test_supported_canvas_can_exceed_generic_string_limit():
    profile = {
        **PROFILE,
        "canvas": {"data_url": "data:image/png;base64," + "A" * 10000},
    }
    assert common.validate_profile(profile) == PROFILE["user_agent"]


def test_application_content_type_matches_generation_before_network(transport):
    with pytest.raises(ValueError, match="Content-Type"):
        run(transport, application_headers={"content-type": "text/plain"})
    assert not transport["sessions"]


def test_profile_language_cannot_inject_fetch_header(transport):
    with pytest.raises(ValueError):
        run(transport, profile={**PROFILE, "language": "en\r\nAuthorization: secret"})
    assert not transport["sessions"]
