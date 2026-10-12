# RayonAPI examples

Small Python examples for the [RayonAPI API](https://api.rayonapi.com) and
[Python SDK](https://github.com/Rayon-API/rayon-sdk-py).

## Install

Python 3.10 or later:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `RAYON_API_KEY` in your environment. Your account must have access to the
requested domain. Do not commit API keys, generated headers or session cookies.

## Starbucks: inspect generated headers

```bash
python -m examples.starbucks_headers
```

Calls `/solve` for the sign-in page and prints the returned six headers. It does
not send a gift-card balance request. Treat the printed headers as transient
session credentials; keep them out of shared logs.

## Southwest: prepare and send a username check

```bash
python -m examples.southwest_username --username dummy_user_123
```

This prepares the example without making requests. To send it, configure the
application's own `SOUTHWEST_API_KEY` and applicable `SOUTHWEST_APP_ID`,
`SOUTHWEST_APP_VERSION`, `SOUTHWEST_CHANNEL_ID` and
`SOUTHWEST_USER_EXPERIENCE_ID` from your authorized integration. These are
application prerequisites, separate from the RayonAPI key.

```bash
python -m examples.southwest_username --username dummy_user_123 --send
```

The example generates fresh telemetry, adds the application headers and JSON
body, and uses `curl_cffi` with Chrome impersonation. It preserves cookie domains
and paths, restricts the destination to the original HTTPS origin, and disables
redirects. The RayonAPI key is sent only to RayonAPI.

`RAYON_REPLAY_PROXY` optionally configures a proxy for the application request.
Keep its IP sticky across your application session. The public `/solve` API does
not currently accept proxy/session parameters or an exact downstream URL/method/
body. Setting a replay proxy therefore does not align the solver's egress or
request context automatically. These examples demonstrate integration; generated
headers alone do not guarantee acceptance by either site. Match the returned
browser profile with a compatible TLS client and validate the complete request.

The API exports four cookie fields only (`name`, `value`, `domain`, `path`);
Secure, expiry and host-only metadata are not a complete browser-session export.
This example applies Secure conservatively and uses a disposable scoped session.

## Development

```bash
pip install -r requirements.txt "pytest>=8,<10"
pytest
```

Tests use local doubles and never call target websites. See the
[documentation](https://rayon-api.github.io/docs/) for the API contract and
[MIT license](LICENSE) for the examples.
