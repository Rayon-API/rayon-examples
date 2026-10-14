# RayonAPI examples

A Python example for client-owned material collection and `POST /v1/shape`.
Your client downloads the full protection JavaScript and supplies a measured browser
profile, current browser cookies, and the exact application URL, method, content type,
and body. RayonAPI generates six request headers; it never fetches the target page
or scripts and returns no target cookies. Your client sends the application request.

[Documentation](https://docs.rayonapi.com/) · [Python SDK](https://github.com/Rayon-API/rayon-sdk-py)

## Setup

Python 3.10+ is required.

```sh
git clone https://github.com/Rayon-API/rayon-examples.git
cd rayon-examples
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p local
```

Dependencies are `rayon-sdk-py>=1.0.2,<2` and `curl_cffi`.
Set `RAYON_API_KEY` in your environment before generation.
The `local/` directory is ignored by Git; keep keys, cookies, bodies, and headers there.

```text
examples/
  common.py            # input validation, collection, generation, exact sending
  request_workflow.py  # runnable CLI
tests/                 # offline transport and cookie tests
requirements.txt
```

## Prepare inputs

Use your own page and application endpoint. The reserved domains below are placeholders.
From the browser/client session you will use, save these files under `local/`:

- `profile.json`: measured supported browser fields, including
  `user_agent` or `navigator.userAgent`, navigator, screen/window, WebGL, and canvas values.
  See [profiles and sessions](https://docs.rayonapi.com/profiles-and-sessions) for the schema.
- `cookies.txt`: current cookies exported in Netscape format, preserving domain,
  path, secure, and expiry scope. Omit `--cookies-file` for an empty session.
  `curl_cffi` can lose imported HttpOnly metadata during its cookie conversion;
  the HTTP jar must not be used to infer JavaScript cookie visibility.
- `document-cookie.txt`: the current browser-visible `document.cookie` string,
  UTF-8 without a trailing newline. An empty file represents an empty string.
  This differs from the HTTP cookie jar: HttpOnly cookies are not browser-visible.
- `request-body.txt`: the exact UTF-8 application body, including any intended whitespace.
  Omit `--body-file` and `--content-type` for a bodyless request.
- `application-headers.json` (optional): a JSON object containing application headers,
  such as `Accept` or application authorization. These are sent only to the application
  endpoint. Cookie, User-Agent, and framing overrides are rejected.

Choose a supported `curl_cffi` impersonation target compatible with your measured
browser. A User-Agent string alone does not establish profile/TLS compatibility.
Select the full script URLs from your integration, including loader and payload
scripts where needed. Repeat `--script-url` in execution order. The example fetches
exactly those URLs; it does not guess scripts or establish that your list is complete.
Obvious HTML challenge responses are rejected as script material. An accepted MIME
type or body does not prove that the selected JavaScript is complete.
See [material preparation](https://docs.rayonapi.com/material).

## Collect, generate, and send

Set `SOURCE_URL`, `REQUEST_URL`, `LOADER_URL`, `PAYLOAD_URL`, and `CHROME_PROFILE`
to values from your integration. For example, `SOURCE_URL` could be
`https://shop.example.com/account` and `REQUEST_URL` could be
`https://shop.example.com/api/check`.

```sh
python -m examples.request_workflow \
  --source-url "$SOURCE_URL" \
  --request-url "$REQUEST_URL" \
  --method POST \
  --content-type application/json \
  --body-file local/request-body.txt \
  --profile local/profile.json \
  --cookies-file local/cookies.txt \
  --document-cookie-file local/document-cookie.txt \
  --headers-file local/application-headers.json \
  --script-url "$LOADER_URL" \
  --script-url "$PAYLOAD_URL" \
  --impersonate "$CHROME_PROFILE" \
  --send
```

Remove `--send` to validate the local inputs offline, without an API key or network
activity. Replace it with `--fetch-and-generate` to fetch the page and selected scripts
and generate headers without sending the application request. Generation can consume
account credit; there is no automatic retry. Output contains only the generation
request ID and, when sending, the application HTTP status. Headers, cookies, and response
bodies are not printed.

With `--send`, a single target session downloads the source page and all selected
scripts, then sends the exact endpoint/method/body using `result.headers`. Its cookie
jar, browser impersonation, User-Agent, and proxy remain consistent. The SDK uses a
separate session for RayonAPI. The API omits canvas from `profile_used`; the example
compares the remaining supplied profile fields before sending, while still supplying
your measured canvas input for generation. Application requests must share the source page's exact
HTTPS origin by default. For an application API on another approved origin, add
`--allow-request-origin https://api.shop.example.com` explicitly (repeat for each
allowed origin). Script URLs may use a different HTTPS host. The shared cookie jar
keeps URL scope; source-page cookies are never flattened into an endpoint Cookie header.

The client verifies TLS and refuses redirects. Ambient proxies are disabled.
Set `RAYON_TARGET_PROXY` explicitly when needed. This HTTP example does not execute
JavaScript or measure browser signals; export fresh profile and cookie data from your
browser integration. Keep the supplied browser-visible cookie snapshot consistent with
any cookies updated during collection. Generation does not guarantee target acceptance.

## Test offline

```sh
python -m pip install 'pytest>=8,<10'
python -m pytest
```

Tests use local transport doubles and real cookie jars; they never contact targets or RayonAPI.

[API reference](https://docs.rayonapi.com/api-reference) · [Support](mailto:support@rayonapi.com) · [MIT license](LICENSE)
