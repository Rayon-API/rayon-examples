"""Client-owned material collection and an optional exact-origin application request."""

import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from curl_cffi import CurlOpt
from curl_cffi.requests import Session
from rayon_sdk_py import Client

PROFILE_FIELDS = {
    "user_agent": str,
    "platform": str,
    "language": str,
    "languages": list,
    "screen": dict,
    "window": dict,
    "webgl": dict,
    "canvas": dict,
    "navigator": dict,
}
PROFILE_SECTIONS = {
    "screen": dict.fromkeys(
        ("width", "height", "availWidth", "availHeight", "colorDepth", "pixelDepth"),
        int,
    ),
    "window": {
        **dict.fromkeys(
            (
                "innerWidth",
                "innerHeight",
                "outerWidth",
                "outerHeight",
                "screenX",
                "screenY",
                "screenLeft",
                "screenTop",
                "pageXOffset",
                "pageYOffset",
            ),
            int,
        ),
        "devicePixelRatio": (int, float),
    },
    "webgl": dict.fromkeys(("renderer", "vendor"), str),
    "canvas": {"data_url": str},
    "navigator": {
        **dict.fromkeys(
            (
                "userAgent",
                "platform",
                "vendor",
                "appVersion",
                "appCodeName",
                "appName",
                "product",
                "language",
            ),
            str,
        ),
        "languages": list,
        "hardwareConcurrency": int,
        "maxTouchPoints": int,
        "webdriver": bool,
        "cookieEnabled": bool,
        "doNotTrack": (str, type(None)),
    },
}


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
    def check(obj, schema):
        if type(obj) is not dict or not obj.keys() <= schema.keys():
            raise ValueError("Unsupported browser profile field")
        for key, value in obj.items():
            expected = schema[key] if isinstance(schema[key], tuple) else (schema[key],)
            if type(value) not in expected:
                raise ValueError("Invalid browser profile field type")
            if isinstance(value, str) and key != "data_url" and len(value) > 8192:
                raise ValueError("Browser profile string is too long")
            if type(value) is float and not math.isfinite(value):
                raise ValueError("Browser profile requires finite numbers")
            if key == "languages" and (
                not 1 <= len(value) <= 32
                or any(type(item) is not str or len(item) > 8192 for item in value)
            ):
                raise ValueError("Invalid browser profile languages")

    check(profile, PROFILE_FIELDS)
    for key, schema in PROFILE_SECTIONS.items():
        if key in profile:
            check(profile[key], schema)
    nav = profile.get("navigator", {})
    for key, alias in [
        ("user_agent", "userAgent"),
        ("platform", "platform"),
        ("language", "language"),
        ("languages", "languages"),
    ]:
        if key in profile and alias in nav and profile[key] != nav[alias]:
            raise ValueError("Conflicting browser profile aliases")
    bounds = {
        "screen": {
            "width": (1, 32768),
            "height": (1, 32768),
            "availWidth": (0, 32768),
            "availHeight": (0, 32768),
            "colorDepth": (1, 64),
            "pixelDepth": (1, 64),
        },
        "window": {
            **dict.fromkeys(
                ("innerWidth", "innerHeight", "outerWidth", "outerHeight"), (1, 32768)
            ),
            "devicePixelRatio": (0.1, 16),
        },
        "navigator": {"hardwareConcurrency": (1, 1024), "maxTouchPoints": (0, 100)},
    }
    for section, fields in bounds.items():
        for key, (lo, hi) in fields.items():
            if (
                key in profile.get(section, {})
                and not lo <= profile[section][key] <= hi
            ):
                raise ValueError("Browser profile value is outside supported bounds")
    canvas = profile.get("canvas", {}).get("data_url")
    if canvas is not None:
        if not re.fullmatch(r"data:image/png;base64,[A-Za-z0-9+/]+={0,2}", canvas):
            raise ValueError("Browser profile canvas must be a PNG data URL")
    if (
        len(
            json.dumps(
                profile, ensure_ascii=True, separators=(",", ":"), allow_nan=False
            ).encode()
        )
        > 64 * 1024
    ):
        raise ValueError("Browser profile exceeds 64 KiB")
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
