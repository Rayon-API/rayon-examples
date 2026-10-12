"""Client-owned material collection and an optional exact-origin application request."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from curl_cffi import CurlOpt
from curl_cffi.requests import Session
from rayon_sdk_py import Client, validate_profile as check_profile


def https_origin(url):
    if (
        not isinstance(url, str)
        or any(ord(c) <= 32 or ord(c) == 127 for c in url)
        or "\\" in url
        or "#" in url
    ):
        raise ValueError("Use a full HTTPS URL without whitespace or a fragment")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Use an HTTPS URL without credentials")
    port = parsed.port if parsed.port is not None else 443
    if not 1 <= port <= 65535:
        raise ValueError("Use a valid HTTPS port")
    return parsed.hostname.lower(), port


def api_key():
    key = os.environ.get("RAYON_API_KEY", "")
    if not key or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError(
            "Set RAYON_API_KEY to a valid ASCII token before calling the API"
        )
    return key


def _strict_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Profile JSON contains duplicate keys")
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise ValueError("Profile JSON must use finite JSON values")


def validate_profile(profile):
    # Reuse the SDK contract; only target HTTP header requirements are additional.
    profile = check_profile(profile)
    nav = profile.get("navigator", {})
    user_agent = profile.get("user_agent") or nav.get("userAgent")
    if not user_agent or any(not 32 <= ord(c) <= 126 for c in user_agent):
        raise ValueError(
            "Browser profile requires a nonempty ASCII user_agent or navigator.userAgent"
        )
    language = profile.get("language") or nav.get("language")
    if language and any(not 32 <= ord(c) <= 126 for c in language):
        raise ValueError("Browser profile language must be safe for an HTTP header")
    return user_agent


def load_profile(path):
    profile = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_strict_pairs,
        parse_constant=_invalid_constant,
    )
    validate_profile(profile)
    return profile


def add_material_arguments(parser):
    parser.add_argument("--profile", help="Path to your supported browser profile JSON")
    parser.add_argument(
        "--script-url",
        action="append",
        default=[],
        help="Full HTTPS protection script URL; repeat in execution order",
    )
    parser.add_argument(
        "--impersonate",
        default="chrome",
        help="Compatible curl_cffi browser target (default: chrome)",
    )


def material_profile(args):
    if not args.profile:
        raise ValueError("Provide --profile with your supported browser profile JSON")
    if not 1 <= len(args.script_url) <= 16:
        raise ValueError("Provide 1 to 16 ordered --script-url values")
    return load_profile(args.profile)


def generate_material(
    source_url,
    script_urls,
    profile,
    request,
    application_headers,
    *,
    send=False,
    client_factory=None,
    session_factory=None,
    impersonate="chrome",
):
    """Collect full sources and generate headers; never replace the target cookie jar."""
    key = api_key()
    if https_origin(source_url) != https_origin(request["url"]):
        raise ValueError(
            "Application request must use the source page's exact HTTPS origin"
        )
    if not 1 <= len(script_urls) <= 16:
        raise ValueError("Provide 1 to 16 explicit script URLs")
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
        raise ValueError("Unsupported application method")
    body = request.get("body")
    if body is not None and (
        not isinstance(body, str) or len(body.encode("utf-8")) > 256 * 1024
    ):
        raise ValueError("Application body must be a UTF-8 string up to 256 KiB")
    content_types = [
        value
        for name, value in application_headers.items()
        if name.lower() == "content-type"
    ]
    if content_types and content_types != [request["content_type"]]:
        raise ValueError("Application Content-Type must match generation context")
    proxy = os.environ.get("RAYON_TARGET_PROXY") or None
    factory = session_factory or Session
    with factory(
        impersonate=impersonate,
        default_headers=False,
        trust_env=False,
        proxy=proxy,
        curl_options={} if proxy else {CurlOpt.PROXY: ""},
    ) as session:
        fetch_headers = {"User-Agent": user_agent}
        language = profile.get("language") or profile.get("navigator", {}).get(
            "language"
        )
        if language:
            fetch_headers["Accept-Language"] = language

        def fetch(url):
            response = session.request(
                "GET",
                url,
                headers=fetch_headers,
                allow_redirects=False,
                verify=True,
                timeout=30,
            )
            if not 200 <= response.status_code < 300:
                raise ValueError(
                    "Material download failed or redirected; provide the final full HTTPS URL"
                )
            return response.text

        fetch(source_url)
        scripts = [{"url": url, "source": fetch(url)} for url in script_urls]
        shape = {
            "source_url": source_url,
            "scripts": scripts,
            "profile": profile,
            "request": dict(request),
        }
        with (client_factory or Client)(api_key=key) as client:
            result = client.generate(shape)
        response = None
        if send:
            if validate_profile(result.profile_used) != user_agent:
                raise ValueError(
                    "Returned browser profile differs from the target session user agent"
                )
            headers = {**fetch_headers, **application_headers}
            if not content_types and request["content_type"] is not None:
                headers["Content-Type"] = request["content_type"]
            headers["User-Agent"] = user_agent
            protected = {name.lower() for name in headers}
            if any(name.lower() in protected for name in result.headers):
                raise ValueError(
                    "Generated header conflicts with an application header"
                )
            headers.update(result.headers)
            response = session.request(
                request["method"],
                request["url"],
                data=body.encode("utf-8") if body is not None else None,
                headers=headers,
                allow_redirects=False,
                verify=True,
                timeout=30,
            )
        return result, response
