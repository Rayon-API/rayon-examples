import json

import pytest

from examples import common


def inputs(tmp_path, profile_file):
    body = tmp_path / "body.txt"
    body.write_bytes(' {"name":"é"}\r\n'.encode())
    cookie = tmp_path / "document-cookie.txt"
    cookie.write_bytes(b"visible=current")
    headers = tmp_path / "headers.json"
    headers.write_text('{"Authorization":"Bearer application-value"}')
    return [
        "--source-url",
        "https://shop.example.com/account",
        "--request-url",
        "https://shop.example.com/api/check",
        "--method",
        "POST",
        "--content-type",
        "application/json",
        "--body-file",
        str(body),
        "--profile",
        str(profile_file),
        "--script-url",
        "https://shop.example.com/loader.js",
        "--script-url",
        "https://cdn.example/payload.js",
        "--document-cookie-file",
        str(cookie),
        "--headers-file",
        str(headers),
        "--impersonate",
        "chrome",
    ]


def test_default_validates_offline_without_api_key(
    tmp_path, profile_file, transport, capsys, monkeypatch
):
    from examples import request_workflow

    monkeypatch.delenv("RAYON_API_KEY", raising=False)
    request_workflow.main(inputs(tmp_path, profile_file), **factories(transport))
    assert not transport["sessions"] and not transport["clients"]
    assert "offline" in capsys.readouterr().out


def factories(transport):
    return {name: transport[name] for name in ("session_factory", "client_factory")}


@pytest.mark.parametrize("mode, count", [("--fetch-and-generate", 3), ("--send", 4)])
def test_live_modes_preserve_order_body_and_hide_secrets(
    tmp_path, profile_file, transport, capsys, monkeypatch, mode, count
):
    from examples import request_workflow

    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    request_workflow.main(
        inputs(tmp_path, profile_file) + [mode], **factories(transport)
    )
    session = transport["sessions"][0]
    assert len(session.calls) == count
    shape = transport["shapes"][0]
    assert [item["url"] for item in shape["scripts"]] == [
        "https://shop.example.com/loader.js",
        "https://cdn.example/payload.js",
    ]
    assert shape["document_cookie"] == "visible=current"
    assert shape["request"]["body"] == ' {"name":"é"}\r\n'
    if mode == "--send":
        assert session.calls[-1][2]["data"] == shape["request"]["body"].encode()
        assert (
            session.calls[-1][2]["headers"]["Authorization"]
            == "Bearer application-value"
        )
    assert all(
        "Authorization" not in options["headers"] for _, _, options in session.calls[:3]
    )
    output = capsys.readouterr().out
    assert all(
        secret not in output
        for secret in ("application-value", "visible=current", "generated", "rayon-key")
    )
    assert len(transport["sessions"]) == len(transport["clients"]) == 1


def test_missing_api_key_precedes_network(
    tmp_path, profile_file, transport, monkeypatch
):
    from examples import request_workflow

    monkeypatch.delenv("RAYON_API_KEY", raising=False)
    with pytest.raises(ValueError, match="RAYON_API_KEY"):
        request_workflow.main(
            inputs(tmp_path, profile_file) + ["--send"], **factories(transport)
        )
    assert not transport["sessions"]


def test_cookie_file_retains_scope_and_http_only_metadata(
    tmp_path, transport, monkeypatch
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    path = tmp_path / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_shop.example.com\tFALSE\t/api\tTRUE\t0\tlogin\tcurrent\n"
        ".example.com\tTRUE\t/\tTRUE\t0\tvisible\tcurrent\n"
        "shop.example.com\tFALSE\t/\tTRUE\t1\texpired\told\n"
    )
    jar = common.load_cookies(path)
    assert {cookie.name for cookie in jar} == {"login", "visible"}
    common.generate_material(
        "https://shop.example.com/account",
        ["https://cdn.example/script.js"],
        {"user_agent": "Owned browser"},
        {
            "url": "https://shop.example.com/api/check",
            "method": "POST",
            "content_type": "text/plain",
            "body": "",
        },
        {},
        cookies=jar,
        document_cookie="visible=current",
        send=True,
        **factories(transport),
    )
    imported = next(
        cookie
        for cookie in transport["sessions"][0].cookies.jar
        if cookie.name == "login"
    )
    assert imported.has_nonstandard_attr("HTTPOnly")
    assert imported.domain == "shop.example.com" and imported.path == "/api"
    assert not imported.domain_specified and imported.secure
    assert imported.expires is None and imported.discard


def test_strict_header_file_rejects_duplicates(tmp_path):
    path = tmp_path / "headers.json"
    path.write_text('{"Accept":"one","Accept":"two"}')
    with pytest.raises(ValueError):
        common.load_headers(path)


def test_published_sdk_receives_complete_material_only_contract(transport, monkeypatch):
    from types import SimpleNamespace

    from curl_cffi.requests import Session
    from rayon_sdk_py import Client, __version__

    assert __version__.split(".")[0] == "1"
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    api_calls = []
    headers = {f"X-Example-{suffix}": "sample" for suffix in "abcdfz"}

    def api_transport(self, method, url, **options):
        # The published SDK validates and serializes the shape before this boundary.
        api_calls.append((method, url, options))
        result = {
            "headers": headers,
            "request_id": "req-example",
            "generation_ms": 1,
            "profile_used": options["json"]["profile"],
            "material_ref": "synthetic_reference_1234",
            "material_expires_at": "2030-01-01T00:00:00Z",
        }
        options["content_callback"](json.dumps(result).encode())
        return SimpleNamespace(status_code=200, headers={})

    monkeypatch.setattr(Session, "request", api_transport)
    result, _ = common.generate_material(
        "https://shop.example.com/account",
        ["https://cdn.example/loader.js"],
        {"user_agent": "Owned browser"},
        {
            "url": "https://shop.example.com/api/check",
            "method": "POST",
            "content_type": "text/plain",
            "body": "exact\r\n",
        },
        {},
        document_cookie="visible=current",
        send=True,
        client_factory=Client,
        session_factory=transport["session_factory"],
    )
    assert len(api_calls) == 1
    method, url, options = api_calls[0]
    assert (method, url) == ("POST", "https://api.rayonapi.com/v1/shape")
    assert set(options["json"]) == {
        "source_url",
        "scripts",
        "profile",
        "request",
        "document_cookie",
    }
    assert options["json"]["scripts"][0]["source"].endswith("*/\n")
    assert options["json"]["document_cookie"] == "visible=current"
    assert transport["sessions"][0].calls[-1][2]["data"] == b"exact\r\n"
    assert result.headers == headers


def test_cli_explicit_subdomain_allowance_and_proxy_keep_credentials_out_of_output(
    tmp_path, profile_file, transport, capsys, monkeypatch
):
    from examples import request_workflow

    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    monkeypatch.setenv(
        "RAYON_TARGET_PROXY", "http://proxy-user:proxy-value@sticky.example:8080"
    )
    args = inputs(tmp_path, profile_file)
    args[args.index("--request-url") + 1] = "https://api.shop.example.com/check"
    args += ["--allow-request-origin", "https://api.shop.example.com", "--send"]
    request_workflow.main(args, **factories(transport))
    assert transport["sessions"][0].calls[-1][1] == "https://api.shop.example.com/check"
    output = capsys.readouterr().out
    assert "proxy-user" not in output and "proxy-value" not in output
