"""Client-owned input validation, material collection, and exact request sending."""

import json
import os
import re
from contextlib import contextmanager
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit

from curl_cffi import CurlOpt
from curl_cffi.requests import Session
from rayon_sdk_py import Client, ValidationError
from rayon_sdk_py import validate_profile as check_profile


class WorkflowInputError(ValueError):
    """An actionable constant message containing no caller or transport data."""


def https_origin(url):
    if (
        not isinstance(url, str)
        or any(ord(c) <= 32 or ord(c) == 127 for c in url)
        or "\\" in url
        or "#" in url
    ):
        raise WorkflowInputError(
            "Use a full HTTPS URL without whitespace or a fragment"
        )
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise WorkflowInputError(
            "Use a valid full HTTPS URL without credentials"
        ) from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise WorkflowInputError("Use an HTTPS URL without credentials")
    try:
        port = parsed.port if parsed.port is not None else 443
    except ValueError:
        raise WorkflowInputError("Use a valid HTTPS port") from None
    if not 1 <= port <= 65535:
        raise WorkflowInputError("Use a valid HTTPS port")
    return parsed.hostname.lower(), port


def api_key():
    key = os.environ.get("RAYON_API_KEY", "")
    if not key or any(not 33 <= ord(c) <= 126 for c in key):
        raise WorkflowInputError(
            "Set RAYON_API_KEY to a valid ASCII token before calling the API"
        )
    return key


def _strict_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise WorkflowInputError("JSON input contains duplicate keys")
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise WorkflowInputError("JSON input must use finite values")


def load_json(path):
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        raise WorkflowInputError(
            "Cannot read JSON input; check --config, --profile or --headers-file paths and UTF-8 encoding"
        ) from None
    try:
        return json.loads(
            text, object_pairs_hook=_strict_pairs, parse_constant=_invalid_constant
        )
    except json.JSONDecodeError:
        raise WorkflowInputError(
            "Invalid JSON input; check --config, --profile or --headers-file JSON syntax"
        ) from None


def validate_profile(profile):
    try:
        profile = check_profile(profile)
    except ValidationError:
        raise WorkflowInputError(
            "Invalid --profile; supply supported measured browser fields without conflicting aliases"
        ) from None
    nav = profile.get("navigator", {})
    user_agent = profile.get("user_agent") or nav.get("userAgent")
    if not user_agent or any(not 32 <= ord(c) <= 126 for c in user_agent):
        raise WorkflowInputError(
            "Browser profile requires a nonempty ASCII user_agent or navigator.userAgent"
        )
    language = profile.get("language") or nav.get("language")
    if language and any(not 32 <= ord(c) <= 126 for c in language):
        raise WorkflowInputError(
            "Browser profile language must be safe for an HTTP header"
        )
    return user_agent


def load_profile(path):
    profile = load_json(path)
    validate_profile(profile)
    return profile


def load_cookies(path):
    """Load scoped Netscape HTTP cookies; do not infer JavaScript visibility."""
    jar = MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, UnicodeError, ValueError):
        raise WorkflowInputError(
            "Cannot load --cookies-file; provide a readable Netscape cookie export"
        ) from None
    # Browser/curl Netscape exports use zero for session-cookie expiry.
    for cookie in jar:
        if cookie.expires == 0:
            cookie.expires = None
            cookie.discard = True
    jar.clear_expired_cookies()
    return jar


def validate_headers(headers):
    if not isinstance(headers, dict):
        raise WorkflowInputError("Application headers must be a JSON object")
    names = set()
    for name, value in headers.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name
        ):
            raise WorkflowInputError("Invalid application header name")
        lowered = name.lower()
        if lowered in names or lowered in {
            "cookie",
            "user-agent",
            "host",
            "content-length",
            "transfer-encoding",
            "accept-language",
        }:
            raise WorkflowInputError(
                "Application header overrides session identity or framing"
            )
        names.add(lowered)
        if not isinstance(value, str) or any(not 32 <= ord(c) <= 126 for c in value):
            raise WorkflowInputError(
                "Application header values must be safe ASCII strings"
            )
    return headers


def load_headers(path):
    return validate_headers(load_json(path))


def validate_inputs(
    source_url,
    script_urls,
    profile,
    request,
    application_headers,
    document_cookie,
    *,
    allow_request_origins=(),
    mode="header",
    form=None,
):
    """Preflight local inputs before opening either network session."""
    allowed = {https_origin(source_url)}
    for origin in allow_request_origins:
        allowed.add(https_origin(origin))
        parsed = urlsplit(origin)
        if parsed.path not in ("", "/") or parsed.query:
            raise WorkflowInputError(
                "Allowed application origin must omit paths and queries"
            )
    if https_origin(request["url"]) not in allowed:
        raise WorkflowInputError(
            "Explicitly allow the application request's HTTPS origin"
        )
    if not 1 <= len(script_urls) <= 16:
        raise WorkflowInputError(
            "Provide 1 to 16 explicit script URLs in execution order"
        )
    for url in script_urls:
        https_origin(url)
    user_agent = validate_profile(profile)
    if request.get("method") not in {
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    }:
        raise WorkflowInputError("Unsupported application method")
    body, content_type = request.get("body"), request.get("content_type")
    if body is not None:
        if not isinstance(body, str) or len(body.encode("utf-8")) > 256 * 1024:
            raise WorkflowInputError(
                "Application body must be a UTF-8 string up to 256 KiB"
            )
        if request["method"] in {"GET", "HEAD"} or not content_type:
            raise WorkflowInputError(
                "A body needs a content type and a body-capable method"
            )
    if content_type is not None:
        if (
            not isinstance(content_type, str)
            or len(content_type) > 256
            or any(ord(c) < 32 or ord(c) == 127 for c in content_type)
        ):
            raise WorkflowInputError("Invalid application content type")
        if not re.fullmatch(
            r"[\w!#$&^.+-]+/[\w!#$&^.+-]+(?:\s*;[^\r\n]*)?", content_type
        ):
            raise WorkflowInputError("Invalid application content type")
        media = content_type.split(";", 1)[0].lower()
        if body is not None and (
            media in {"application/octet-stream", "application/pdf", "application/zip"}
            or media.startswith(("image/", "audio/", "video/", "multipart/"))
        ):
            raise WorkflowInputError(
                "Use a UTF-8 text body; binary and multipart bodies are unsupported"
            )
    validate_headers(application_headers)
    for name, value in application_headers.items():
        if name.lower() == "content-type" and value != content_type:
            raise WorkflowInputError(
                "Application Content-Type must match generation context"
            )
    if (
        not isinstance(document_cookie, str)
        or len(document_cookie.encode("utf-8")) > 16 * 1024
        or any(ord(c) < 32 or ord(c) == 127 for c in document_cookie)
    ):
        raise WorkflowInputError(
            "Document cookie must be current UTF-8 text without control characters, up to 16 KiB"
        )
    validate_form(mode, form, request)
    return user_agent


def validate_form(mode, form, request):
    """Check form context locally without changing application field encoding."""
    if mode not in ("header", "form"):
        raise WorkflowInputError("Use mode header or form")
    if mode == "header":
        if form is not None:
            raise WorkflowInputError("Form metadata requires mode form")
        return
    if request["method"] != "POST" or not re.fullmatch(
        r'application/x-www-form-urlencoded(?:\s*;\s*charset\s*=\s*(?:"(?:utf-8|utf8)"|utf-8|utf8))?\s*',
        request.get("content_type") or "", re.I,
    ):
        raise WorkflowInputError(
            "Form mode needs POST and application/x-www-form-urlencoded with optional UTF-8 charset"
        )
    if form is not None and (
        not isinstance(form, dict) or not form.keys() <= {"id", "name"}
        or any(not isinstance(value, str) or len(value) > 256
               or any(ord(c) < 32 or ord(c) == 127 for c in value)
               for value in form.values())
    ):
        raise WorkflowInputError("Form metadata accepts only id and name strings up to 256 characters")
    body = request.get("body")
    if not isinstance(body, str) or re.search(r"%(?![0-9A-Fa-f]{2})", body):
        raise WorkflowInputError("Provide the original UTF-8 URL-encoded form body before telemetry insertion")
    families, count = {}, 0
    try:
        for value in (form or {}).values():
            value.encode("utf-8", errors="strict")
        for part in body.split("&"):
            if not part:
                continue
            count += 1
            name, _, value = part.partition("=")
            name, value = (unquote_plus(item, encoding="utf-8", errors="strict")
                           for item in (name, value))
            if "\x00" in name or "\x00" in value or len(name.encode("utf-8")) > 256 or count > 1024:
                raise ValueError
            match = re.fullmatch(r"([!#$%&'*+\-.^_`|~0-9A-Za-z]{1,128})([abcdfz])", name)
            if match:
                families.setdefault(match[1], set()).add(match[2])
        if any(slots == set("abcdfz") for slots in families.values()):
            raise ValueError
    except (ValueError, UnicodeError):
        raise WorkflowInputError(
            "Provide a valid UTF-8 URL-encoded form with at most 1024 fields and no existing telemetry family"
        ) from None


@contextmanager
def workflow_stage(name):
    """Attach only a constant stage label while preserving the original exception."""
    try:
        yield
    except Exception as error:
        error._workflow_stage = name
        raise


def _same_supplied_fields(supplied, used):
    if isinstance(supplied, dict):
        return isinstance(used, dict) and all(
            key in used and _same_supplied_fields(value, used[key])
            for key, value in supplied.items()
        )
    return supplied == used


def generate_material(
    source_url,
    script_urls,
    profile,
    request,
    application_headers,
    *,
    document_cookie="",
    cookies=None,
    send=False,
    client_factory=None,
    session_factory=None,
    impersonate="chrome",
    allow_request_origins=(),
    mode="header",
    form=None,
):
    """Fetch explicit material, generate, and optionally send through the same session."""
    key = api_key()
    user_agent = validate_inputs(
        source_url,
        script_urls,
        profile,
        request,
        application_headers,
        document_cookie,
        allow_request_origins=allow_request_origins,
        mode=mode,
        form=form,
    )
    proxy = os.environ.get("RAYON_TARGET_PROXY") or None
    with (session_factory or Session)(
        impersonate=impersonate,
        default_headers=False,
        trust_env=False,
        proxy=proxy,
        curl_options={} if proxy else {CurlOpt.PROXY: ""},
        cookies=cookies,
    ) as session:
        fetch_headers = {"User-Agent": user_agent}
        language = profile.get("language") or profile.get("navigator", {}).get(
            "language"
        )
        if language:
            fetch_headers["Accept-Language"] = language

        def fetch(url):
            with workflow_stage("collection"):
                response = session.request(
                    "GET", url, headers=fetch_headers, allow_redirects=False,
                    verify=True, timeout=30,
                )
            if not 200 <= response.status_code < 300:
                raise WorkflowInputError(
                    "Material download failed or redirected; provide the final full HTTPS URL"
                )
            return response

        fetch(source_url)
        scripts = []
        total = 0
        for url in script_urls:
            download = fetch(url)
            source = download.content.decode("utf-8")
            media_type = (
                download.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if media_type in {"text/html", "application/xhtml+xml"} or re.match(
                r"\A[\s\ufeff]*(?:<!doctype\s+html\b|<(?:html|head|body|title|meta|script)\b|<\?xml\b)",
                source,
                re.IGNORECASE,
            ):
                raise WorkflowInputError(
                    "Protection script download returned HTML; refresh the selected script material"
                )
            size = len(source.encode("utf-8"))
            total += size
            if not source or size > 2 * 1024 * 1024 or total > 3 * 1024 * 1024:
                raise WorkflowInputError(
                    "Protection script is empty or exceeds material size limits"
                )
            scripts.append({"url": url, "source": source})
        shape = {
            "source_url": source_url,
            "scripts": scripts,
            "profile": profile,
            "request": dict(request),
            "document_cookie": document_cookie,
        }
        if mode == "form":
            shape["mode"] = "form"
            if form is not None:
                shape["form"] = dict(form)
        with workflow_stage("generation"):
            with (client_factory or Client)(api_key=key) as client:
                result = client.generate(shape)
        response = None
        if send:
            # The API omits canvas from profile_used; compare every reported supplied field.
            reported_fields = {
                name: value for name, value in profile.items() if name != "canvas"
            }
            if validate_profile(
                result.profile_used
            ) != user_agent or not _same_supplied_fields(
                reported_fields, result.profile_used
            ):
                raise WorkflowInputError(
                    "Returned browser profile differs from the measured target session profile"
                )
            headers = {**fetch_headers, **application_headers}
            if request["content_type"] is not None and not any(
                name.lower() == "content-type" for name in headers
            ):
                headers["Content-Type"] = request["content_type"]
            body = request["body"]
            if mode == "form":
                body = result.form_body + ("&" + body if body else "")
            else:
                protected = {name.lower() for name in headers} | {
                    "cookie", "host", "content-length", "transfer-encoding",
                }
                if any(name.lower() in protected for name in result.headers):
                    raise WorkflowInputError(
                        "Generated header conflicts with a session or application header"
                    )
                headers.update(result.headers)
            with workflow_stage("application"):
                response = session.request(
                    request["method"], request["url"],
                    data=body.encode("utf-8") if body is not None else None,
                    headers=headers, allow_redirects=False, verify=True, timeout=30,
                )
        return result, response
