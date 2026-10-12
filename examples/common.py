"""Cookie-scoped replay for one explicitly selected HTTPS origin."""

import os
from urllib.parse import urlsplit

from curl_cffi import CurlOpt
from curl_cffi.requests import Cookies, Session


def https_origin(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("Use an HTTPS URL without credentials or a fragment")
    port = parsed.port if parsed.port is not None else 443
    if not 1 <= port <= 65535:
        raise ValueError("Use a valid HTTPS port")
    return parsed.hostname.lower(), port


def scoped_cookies(rows, source_url):
    host, _ = https_origin(source_url)
    cookies = Cookies()
    for row in rows:
        domain = row["domain"].lstrip(".").lower()
        if not domain or not (host == domain or host.endswith("." + domain)):
            continue
        # The API omits Secure/host-only metadata; limit replay to one HTTPS origin.
        cookies.set(
            row["name"],
            row["value"],
            domain=row["domain"],
            path=row["path"],
            secure=True,
        )
    return cookies


def replay_once(
    result,
    source_url,
    endpoint,
    method,
    body,
    application_headers,
    *,
    session_factory=None,
):
    if https_origin(source_url) != https_origin(endpoint):
        raise ValueError("Replay must use the original target's exact HTTPS origin")
    headers = {**application_headers, **result.headers}
    profile = result.profile_used
    navigator = profile.get("navigator")
    if not isinstance(navigator, dict):
        navigator = {}
    user_agent = (
        navigator.get("userAgent")
        or profile.get("userAgent")
        or profile.get("user_agent")
    )
    if user_agent:
        headers["User-Agent"] = user_agent
    factory = session_factory or Session
    proxy = os.environ.get("RAYON_REPLAY_PROXY")
    with factory(
        impersonate="chrome",
        trust_env=False,
        proxy=proxy,
        curl_options={} if proxy else {CurlOpt.PROXY: ""},
    ) as session:
        return session.request(
            method,
            endpoint,
            data=body,
            headers=headers,
            cookies=scoped_cookies(result.cookies, source_url),
            allow_redirects=False,
            timeout=30,
        )


def api_key():
    key = os.environ.get("RAYON_API_KEY", "")
    if not key:
        raise ValueError("Set RAYON_API_KEY before calling the API")
    return key
