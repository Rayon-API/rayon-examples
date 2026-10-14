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


def test_profile_preflight_uses_utf8_effective_limits_for_unicode():
    from examples.common import validate_profile

    profile = {
        "user_agent": "Browser",
        "navigator": {"vendor": "é" * 8192, "appName": "é" * 8192},
    }
    assert validate_profile(profile) == "Browser"


def test_profile_preflight_rejects_out_of_range_coordinates():
    from examples.common import validate_profile

    with pytest.raises(ValueError):
        validate_profile({"user_agent": "Browser", "window": {"screenX": 2147483648}})


def test_current_document_cookie_is_supplied_as_material(transport):
    run(transport, document_cookie="visible=current")
    assert transport["shapes"][0]["document_cookie"] == "visible=current"
    assert not any(
        "Cookie" in call[2]["headers"] for call in transport["sessions"][0].calls
    )


@pytest.mark.parametrize(
    "cookie",
    ["bad\nvalue", "bad\x00value", "x" * 16385],
    ids=["newline", "null", "oversized"],
)
def test_document_cookie_validation_precedes_network(transport, cookie):
    with pytest.raises(ValueError):
        run(transport, document_cookie=cookie)
    assert not transport["sessions"]


@pytest.mark.parametrize(
    "body, content_type, method",
    [
        ("body", None, "POST"),
        ("body", "text/plain", "GET"),
        ("body", "multipart/form-data", "POST"),
        ("body", "application/json\r\nInjected: true", "POST"),
    ],
)
def test_invalid_context_precedes_material_network(
    transport, body, content_type, method
):
    with pytest.raises(ValueError):
        run(
            transport,
            request={
                **REQUEST,
                "body": body,
                "content_type": content_type,
                "method": method,
            },
        )
    assert not transport["sessions"]


@pytest.mark.parametrize(
    "source", ["", "x" * (2 * 1024 * 1024 + 1)], ids=["empty", "oversized"]
)
def test_empty_or_oversized_script_stops_before_api(transport, source):
    transport["source"] = source
    with pytest.raises(ValueError):
        run(transport)
    assert not transport["clients"]
    assert transport["sessions"][0].closed


def test_changed_measured_profile_stops_send(transport):
    transport["profile_used"] = {**PROFILE, "screen": {"width": 800}}
    with pytest.raises(ValueError, match="profile"):
        run(transport, profile={**PROFILE, "screen": {"width": 1600}})
    assert all(call[0] == "GET" for call in transport["sessions"][0].calls)


@pytest.mark.parametrize(
    "headers",
    [
        {"Cookie": "flattened=wrong"},
        {"User-Agent": "wrong"},
        {"Authorization": "bad\nvalue"},
    ],
)
def test_unsafe_application_headers_rejected_before_network(transport, headers):
    with pytest.raises(ValueError):
        run(transport, application_headers=headers)
    assert not transport["sessions"]


def test_source_page_encoding_does_not_change_script_material(transport):
    transport["contents"] = {SOURCE: b"<p>\xe9</p>"}
    run(transport)
    assert transport["shapes"][0]["scripts"][0]["source"].endswith("*/\n")


def test_invalid_script_utf8_stops_before_generation(transport):
    transport["contents"] = {"https://cdn.example/selected.js": b"\xff"}
    with pytest.raises(UnicodeError):
        run(transport)
    assert not transport["clients"]


def test_explicit_application_origin_allows_subdomain_without_forwarding_headers(
    transport,
):
    endpoint = "https://api.shop.example.com/check"
    run(
        transport,
        request={**REQUEST, "url": endpoint},
        allow_request_origins=["https://api.shop.example.com"],
    )
    calls = transport["sessions"][0].calls
    assert calls[-1][1] == endpoint
    assert transport["shapes"][0]["request"]["url"] == endpoint
    assert all("x-api-key" not in options["headers"] for _, _, options in calls[:-1])
    assert calls[-1][2]["headers"]["x-api-key"] == "app-key"
    assert not any("Cookie" in options["headers"] for _, _, options in calls)


@pytest.mark.parametrize(
    "origin",
    [
        "http://api.shop.example.com",
        "https://api.shop.example.com/path",
        "https://api.shop.example.com?query",
        "https://user:password@api.shop.example.com",
    ],
)
def test_allow_request_origin_requires_exact_https_origin_before_network(
    transport, origin
):
    with pytest.raises(ValueError):
        run(transport, allow_request_origins=[origin])
    assert not transport["sessions"]


def test_unlisted_application_origin_rejected_even_with_other_allowance(transport):
    with pytest.raises(ValueError):
        run(
            transport,
            request={**REQUEST, "url": "https://other.shop.example.com/check"},
            allow_request_origins=["https://api.shop.example.com"],
        )
    assert not transport["sessions"]


def test_response_profile_can_omit_canvas_and_expand_defaults(
    transport, canvas_data_url
):
    supplied = {
        **PROFILE,
        "canvas": {"data_url": canvas_data_url},
        "screen": {"width": 1600},
    }
    transport["profile_used"] = {
        **PROFILE,
        "screen": {"width": 1600, "height": 900},
        "navigator": {"userAgent": PROFILE["user_agent"], "language": "en-US"},
    }
    run(transport, profile=supplied)
    assert transport["sessions"][0].calls[-1][0] == "POST"
    assert transport["shapes"][0]["profile"] == supplied


@pytest.mark.parametrize(
    "mime, source",
    [
        ("text/html; charset=UTF-8", "/* misleading non-HTML prefix */"),
        ("application/xhtml+xml", "<html><body>challenge</body></html>"),
        ("application/javascript", "\ufeff \n<!DOCTYPE HTML><html>challenge</html>"),
        ("text/plain", " \r\n<html>challenge</html>"),
        ("", "\ufeff\n<head><title>challenge</title></head>"),
    ],
    ids=["html-mime", "xhtml-mime", "doctype-bom", "html-body", "head-bom"],
)
def test_html_script_response_stops_before_api(transport, mime, source):
    transport["response_headers"] = {"Content-Type": mime}
    transport["source"] = source
    with pytest.raises(ValueError, match="HTML"):
        run(transport)
    assert not transport["clients"] and not transport["shapes"]
    assert transport["sessions"][0].closed


@pytest.mark.parametrize(
    "mime",
    ["text/plain", "application/octet-stream", "", "text/javascript;charset=utf-8"],
)
def test_script_with_unusual_mime_preserves_full_source(transport, mime):
    transport["response_headers"] = {"Content-Type": mime}
    transport["source"] = "\ufeff\n/* owned JavaScript */\nconst example = 1;\n"
    run(transport)
    assert transport["shapes"][0]["scripts"][0]["source"] == transport["source"]
