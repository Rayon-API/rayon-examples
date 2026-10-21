"""Offline first-run configuration, form sending, and safe failure guidance."""

import json
from types import SimpleNamespace

import pytest

from examples import common, request_workflow
from test_workflow import factories, inputs


def config_file(tmp_path, profile_file, **changes):
    data = {
        "source_url": "https://shop.example.com/account",
        "request_url": "https://shop.example.com/api/check",
        "method": "POST",
        "profile": profile_file.name,
        "script_urls": ["https://cdn.example/payload.js"],
        "impersonate": "chrome",
    }
    data.update(changes)
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(data))
    return path


def test_config_is_offline_with_empty_cookie_default(
    tmp_path, profile_file, transport, monkeypatch, capsys
):
    monkeypatch.delenv("RAYON_API_KEY", raising=False)
    path = config_file(tmp_path, profile_file)
    request_workflow.main(["--config", str(path)], **factories(transport))
    assert "offline" in capsys.readouterr().out
    assert not transport["sessions"] and not transport["clients"]


def test_config_paths_are_relative_to_config_and_preserve_bytes(
    tmp_path, profile_file, transport, monkeypatch
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    (tmp_path / "body.txt").write_bytes(b"a=one&a=two\r\n")
    (tmp_path / "cookie.txt").write_bytes(b"visible=current")
    (tmp_path / "headers.json").write_text('{"Accept":"text/plain"}')
    (tmp_path / "cookies.txt").write_text("# Netscape HTTP Cookie File\n")
    path = config_file(
        tmp_path, profile_file, body_file="body.txt", content_type="text/plain",
        document_cookie_file="cookie.txt", headers_file="headers.json",
        cookies_file="cookies.txt",
    )
    monkeypatch.chdir(tmp_path.parent)
    request_workflow.main(["--config", str(path), "--send"], **factories(transport))
    shape = transport["shapes"][0]
    assert shape["document_cookie"] == "visible=current"
    assert shape["request"]["body"] == "a=one&a=two\r\n"
    assert transport["sessions"][0].calls[-1][2]["data"] == b"a=one&a=two\r\n"


def test_explicit_flags_override_config_including_repeated_lists(
    tmp_path, profile_file, transport, monkeypatch
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    path = config_file(tmp_path, profile_file, method="GET",
                       request_url="https://wrong.example/api",
                       allow_request_origins=["https://wrong.example"])
    request_workflow.main([
        "--config", str(path), "--method", "POST", "--request-url",
        "https://api.shop.example.com/check", "--allow-request-origin",
        "https://api.shop.example.com", "--script-url", "https://cdn.example/new.js",
        "--impersonate", "chrome136", "--fetch-and-generate",
    ], **factories(transport))
    shape = transport["shapes"][0]
    assert shape["request"]["method"] == "POST"
    assert [s["url"] for s in shape["scripts"]] == ["https://cdn.example/new.js"]
    assert shape["document_cookie"] == ""
    assert transport["sessions"][0].options["impersonate"] == "chrome136"


@pytest.mark.parametrize("changes", [
    {"send": True}, {"fetch_and_generate": True}, {"api_key": "private-marker"},
    {"network": True}, {"unexpected": "private-marker"}, {"script_urls": "https://cdn.example/x"},
    {"allow_request_origins": "https://shop.example.com"}, {"profile": {}},
    {"source_url": None}, {"method": False}, {"impersonate": ""},
    {"mode": "unexpected"}, {"form": {"unexpected": "private-marker"}},
])
def test_bad_config_is_rejected_before_network_without_echo(
    tmp_path, profile_file, transport, changes
):
    path = config_file(tmp_path, profile_file, **changes)
    with pytest.raises(SystemExit) as failure:
        request_workflow.cli(["--config", str(path), "--send"], **factories(transport))
    assert "Input error" in str(failure.value.code)
    assert "private-marker" not in str(failure.value.code)
    assert not transport["sessions"] and not transport["clients"]


@pytest.mark.parametrize("raw", ["[]", "null", '{"method":"GET","method":"POST"}', '{"mode":NaN}'])
def test_config_json_is_strict(tmp_path, transport, raw):
    path = tmp_path / "workflow.json"
    path.write_text(raw)
    with pytest.raises(SystemExit, match="Input error"):
        request_workflow.cli(["--config", str(path)], **factories(transport))
    assert not transport["sessions"]


def test_cli_cookie_snapshot_is_optional(tmp_path, profile_file, transport):
    args = inputs(tmp_path, profile_file)
    i = args.index("--document-cookie-file")
    del args[i:i + 2]
    request_workflow.main(args, **factories(transport))
    assert not transport["sessions"]


def form_run(transport, **changes):
    kwargs = dict(
        source_url="https://shop.example.com/account",
        script_urls=["https://cdn.example/script.js"],
        profile={"user_agent": "Owned browser"},
        request={"url": "https://shop.example.com/api/check", "method": "POST",
                 "content_type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "body": "a=one&a=two&space=%20&plus=+&accent=%C3%A9"},
        application_headers={}, mode="form", form={"id": "checkout", "name": "order"},
        send=True, **factories(transport),
    )
    kwargs.update(changes)
    return common.generate_material(**kwargs)


@pytest.mark.parametrize("body", ["a=one&a=two&space=%20&plus=+&accent=%C3%A9", "", "a=1&"])
def test_form_prefixes_returned_body_exactly_once_without_header_result(
    transport, monkeypatch, body
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    telemetry = "telemetrya=one&telemetryb=two"

    def generate(self, shape):
        transport["shapes"].append(shape)
        return SimpleNamespace(form_body=telemetry, profile_used=shape["profile"], request_id="req-form")

    monkeypatch.setattr(transport["client_factory"], "generate", generate)
    request = {"url": "https://shop.example.com/api/check", "method": "POST",
               "content_type": "application/x-www-form-urlencoded", "body": body}
    form_run(transport, request=request)
    shape = transport["shapes"][0]
    assert shape["mode"] == "form" and shape["form"] == {"id": "checkout", "name": "order"}
    assert shape["request"]["body"] == body
    expected = telemetry + ("&" + body if body else "")
    assert transport["sessions"][0].calls[-1][2]["data"] == expected.encode()


@pytest.mark.parametrize("changes", [
    {"mode": "unknown"}, {"mode": "header", "form": {}},
    {"form": {"id": "bad\nvalue"}}, {"form": {"name": "x" * 257}},
    {"form": {"id": False}}, {"form": {"other": "value"}}, {"form": {"id": "\ud800"}},
    {"request": {"url": "https://shop.example.com/api", "method": "PUT",
                 "content_type": "application/x-www-form-urlencoded", "body": "x=1"}},
    {"request": {"url": "https://shop.example.com/api", "method": "POST",
                 "content_type": "application/json", "body": "{}"}},
    *[{"request": {"url": "https://shop.example.com/api", "method": "POST",
                   "content_type": "application/x-www-form-urlencoded", "body": body}}
      for body in [None, "x=%GG", "x=%FF", "x=%00", "x" * 257 + "=1",
                   "&".join("x=1" for _ in range(1025)),
                   "&".join("telemetry" + suffix + "=1" for suffix in "abcdfz")]],
])
def test_form_errors_are_checked_offline_before_network(transport, monkeypatch, changes):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    with pytest.raises(common.WorkflowInputError):
        form_run(transport, **changes)
    assert not transport["sessions"] and not transport["clients"]


def test_form_config_and_cli_metadata_override_validate_offline(tmp_path, profile_file, transport):
    (tmp_path / "form.txt").write_text("x=1&x=2")
    path = config_file(tmp_path, profile_file, mode="form", form={"id": "checkout"},
                       content_type="application/x-www-form-urlencoded", body_file="form.txt")
    request_workflow.main(["--config", str(path), "--form-name", "order"], **factories(transport))
    assert not transport["sessions"]


@pytest.mark.parametrize("billing", ["not_charged", "pending", "unknown", None])
def test_sdk_guidance_shows_trusted_reason_action_billing_and_stage(
    tmp_path, profile_file, transport, monkeypatch, billing
):
    from rayon_sdk_py import HTTPError

    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")

    def fail(self, shape):
        raise HTTPError("private-marker", code="generation_timeout", request_id="req-safe",
                        reason="generation_timeout", action="private-marker", retryable=True,
                        billing_status=billing)

    monkeypatch.setattr(transport["client_factory"], "generate", fail)
    with pytest.raises(SystemExit) as failure:
        request_workflow.cli(inputs(tmp_path, profile_file) + ["--send"], **factories(transport))
    message = str(failure.value.code)
    assert "reason: generation_timeout" in message and "request ID: req-safe" in message
    assert "generation" in message and "application request was not sent" in message
    assert "private-marker" not in message
    if billing == "not_charged":
        assert "billing: not_charged" in message and "Retry once with backoff" in message
    else:
        assert "Check request history" in message


def test_untrusted_error_guidance_and_billing_are_not_printed(
    tmp_path, profile_file, transport, monkeypatch
):
    from rayon_sdk_py import HTTPError

    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")

    def fail(self, shape):
        raise HTTPError("private-marker", code="unknown", reason="private-marker",
                        action="private-marker", billing_status="private-marker")

    monkeypatch.setattr(transport["client_factory"], "generate", fail)
    with pytest.raises(SystemExit) as failure:
        request_workflow.cli(inputs(tmp_path, profile_file) + ["--send"], **factories(transport))
    assert "private-marker" not in str(failure.value.code)
    assert "Check request history" in str(failure.value.code)


@pytest.mark.parametrize("failure_stage", ["collection", "application"])
def test_transport_guidance_distinguishes_before_and_after_generation(
    tmp_path, profile_file, transport, monkeypatch, failure_stage
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    original = transport["session_factory"].request

    def fail(self, method, url, **options):
        if failure_stage == "collection" or method == "POST":
            raise RuntimeError("private-marker proxy-secret")
        return original(self, method, url, **options)

    monkeypatch.setattr(transport["session_factory"], "request", fail)
    with pytest.raises(SystemExit) as failure:
        request_workflow.cli(inputs(tmp_path, profile_file) + ["--send"], **factories(transport))
    message = str(failure.value.code)
    assert "private-marker" not in message and "proxy-secret" not in message
    if failure_stage == "collection":
        assert "generation and the application request were not sent" in message
        assert not transport["clients"]
    else:
        assert "acceptance is unknown" in message and "request history" in message
        assert transport["clients"]


def test_published_sdk_form_contract_without_result_headers(transport, monkeypatch):
    from curl_cffi.requests import Session
    from rayon_sdk_py import Client, FormShapeResult

    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    fields = {"telemetry" + suffix: "value" for suffix in "abcdfz"}
    telemetry = "&".join(name + "=" + value for name, value in fields.items())
    api_calls = []

    def api_transport(self, method, url, **options):
        api_calls.append(options["json"])
        options["content_callback"](json.dumps({
            "form_fields": fields, "form_body": telemetry,
            "profile_used": options["json"]["profile"], "request_id": "req-form",
            "generation_ms": 1, "material_ref": "synthetic_reference_1234",
            "material_expires_at": "2030-01-01T00:00:00Z",
        }).encode())
        return SimpleNamespace(status_code=200, headers={})

    monkeypatch.setattr(Session, "request", api_transport)
    result, response = form_run(transport, client_factory=Client)
    assert isinstance(result, FormShapeResult) and not hasattr(result, "headers")
    assert len(api_calls) == 1 and api_calls[0]["mode"] == "form"
    assert transport["sessions"][0].calls[-1][2]["data"] == (
        telemetry + "&" + api_calls[0]["request"]["body"]
    ).encode()
    assert response.status_code == 200


def test_config_form_metadata_overrides_and_generate_only(
    tmp_path, profile_file, transport, monkeypatch
):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    (tmp_path / "body.txt").write_bytes(b"x=1&x=2")
    path = config_file(tmp_path, profile_file, mode="form", form={"id": "old", "name": "order"},
                       content_type="application/x-www-form-urlencoded", body_file="body.txt")
    request_workflow.main([
        "--config", str(path), "--form-id", "new", "--fetch-and-generate",
    ], **factories(transport))
    shape = transport["shapes"][0]
    assert shape["mode"] == "form" and shape["form"] == {"id": "new", "name": "order"}
    assert shape["request"]["body"] == "x=1&x=2"
    assert all(method == "GET" for method, _, _ in transport["sessions"][0].calls)


def test_cli_file_override_uses_current_directory(tmp_path, profile_file, transport, monkeypatch):
    monkeypatch.setenv("RAYON_API_KEY", "rayon-key")
    path = config_file(tmp_path, profile_file)
    other = tmp_path / "another"
    other.mkdir()
    (other / "profile.json").write_text('{"user_agent":"CLI browser"}')
    monkeypatch.chdir(other)
    request_workflow.main([
        "--config", str(path), "--profile", "profile.json", "--fetch-and-generate",
    ], **factories(transport))
    assert transport["shapes"][0]["profile"]["user_agent"] == "CLI browser"
