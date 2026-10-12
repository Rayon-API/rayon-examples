import json

import pytest

from examples import southwest_username, starbucks_headers


def options(profile_file):
    return [
        "--profile",
        str(profile_file),
        "--script-url",
        "https://cdn.example/protection.js",
        "--script-url",
        "https://www.southwest.com/second.js",
    ]


def factories(transport):
    return {key: transport[key] for key in ("client_factory", "session_factory")}


def test_starbucks_collects_explicit_ordered_material_prints_headers_and_never_posts(
    monkeypatch, profile_file, transport, capsys
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-secret")
    starbucks_headers.main(options(profile_file), **factories(transport))
    shape = transport["shapes"][0]
    assert shape["source_url"] == starbucks_headers.SOURCE_URL
    assert [item["url"] for item in shape["scripts"]] == [
        "https://cdn.example/protection.js",
        "https://www.southwest.com/second.js",
    ]
    assert all(
        item["source"] == "/* full source: " + item["url"] + " */\n"
        for item in shape["scripts"]
    )
    assert shape["request"] == {
        "url": "https://www.starbucks.com/apiproxy/v1/gift/card/check-balance",
        "method": "POST",
        "content_type": "application/json",
        "body": '{"cardNumber":"0000000000000000","pin":"00000000"}',
    }
    assert shape["profile"] == {
        "user_agent": "Owned Chrome browser",
        "language": "en-GB",
    }
    assert [call[0] for call in transport["sessions"][0].calls] == ["GET", "GET", "GET"]
    assert json.loads(capsys.readouterr().out) == {"X-Owned-a": "generated"}
    assert transport["clients"][0].closed and transport["sessions"][0].closed


def test_southwest_default_is_offline(monkeypatch, transport, capsys):
    southwest_username.main([], **factories(transport))
    assert not transport["sessions"] and not transport["clients"]
    assert "--send" in capsys.readouterr().out


def test_southwest_sends_same_utf8_body_in_same_session_with_required_headers(
    monkeypatch, profile_file, transport
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-secret")
    for header, variable in southwest_username.APPLICATION_ENV.items():
        monkeypatch.setenv(variable, variable + "-value")
    southwest_username.main(
        options(profile_file) + ["--send", "--username", "dummy_é"],
        **factories(transport),
    )
    assert len(transport["sessions"]) == len(transport["clients"]) == 1
    session = transport["sessions"][0]
    method, url, sent = session.calls[-1]
    shape = transport["shapes"][0]
    assert (method, url) == ("POST", southwest_username.ENDPOINT)
    assert shape["request"]["url"] == url and shape["request"]["method"] == method
    assert sent["data"] == shape["request"]["body"].encode("utf-8")
    assert json.loads(sent["data"]) == {"username": "dummy_é"}
    assert sent["headers"]["Content-Type"] == shape["request"]["content_type"]
    for header, variable in southwest_username.APPLICATION_ENV.items():
        assert sent["headers"][header] == variable + "-value"
    assert sent["headers"]["User-Agent"] == "Owned Chrome browser"
    assert sent["headers"]["Accept-Language"] == "en-GB"
    assert sent["headers"]["X-Owned-a"] == "generated"
    assert "rayon-secret" not in str(session.options) + str(session.calls)
    assert not any("cookies" in call[2] for call in session.calls)
    assert next(iter(session.cookies.jar)).value == "fresh"
    assert all(call[2]["allow_redirects"] is False for call in session.calls)
    assert all(call[2]["verify"] is True for call in session.calls)
    assert all(
        call[2]["headers"]["User-Agent"] == "Owned Chrome browser"
        for call in session.calls
    )
    assert all(
        not any(k.lower() in {"authorization", "x-api-key"} for k in call[2]["headers"])
        for call in session.calls[:-1]
    )
    assert session.closed and transport["clients"][0].closed


@pytest.mark.parametrize("missing", ["RAYON_API_KEY", "SOUTHWEST_API_KEY"])
def test_required_credentials_precede_profile_and_any_network(
    monkeypatch, transport, missing
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    monkeypatch.setenv("SOUTHWEST_API_KEY", "application-key")
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError, match=missing):
        southwest_username.main(["--send"], **factories(transport))
    assert not transport["sessions"] and not transport["clients"]
