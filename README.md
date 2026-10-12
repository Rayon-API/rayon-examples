# RayonAPI examples

Client-owned material preparation for [RayonAPI](https://api.rayonapi.com) and the
[Python SDK](https://github.com/Rayon-API/rayon-sdk-py) 1.0. RayonAPI generates
request headers through `POST /v1/shape`; it does not fetch target pages, discover
scripts, create a browser session, or return cookies.

## Install

Python 3.10 or later:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The requirements target `rayon-sdk-py>=1.0,<2`. Until SDK 1.0 is published to the
package registry, use an approved local checkout of the SDK's 1.0 source:

```bash
pip install 'curl_cffi>=0.13,<1' 'pytest>=8,<10'
export PYTHONPATH=/absolute/path/to/rayon-sdk-py/src
```

Set `RAYON_API_KEY` in your environment. Your account must have access to the
requested target. Keep keys, profiles, downloaded protection source, generated
headers and session cookies outside this public repository and shared logs.

## Prepare material and a profile

Use your authorized browser integration to select the full HTTPS URLs of the
protection scripts needed for the chosen source page. Supply `--script-url` once
per script, in execution order (1–16 scripts). A selected script may be served
by a CDN. The examples download only the page and your explicit URLs. They do
not identify protection by a hardcoded header prefix, crawl page scripts, or
upload all application JavaScript. Script source is sent in full to RayonAPI;
script URLs alone are insufficient. Each script must fit the API's 2 MiB limit,
with at most 3 MiB of script source in total.

Supply `--profile /absolute/path/to/owned-profile.json` from your client-owned
browser profile. This is a strict JSON object using the SDK's supported fields:
`user_agent`, `platform`, `language`, `languages`, `screen`, `window`, `webgl`,
`canvas`, and `navigator`. Nested fields must follow the SDK schema. Unknown
fields, duplicate JSON keys, non-finite numbers, conflicting aliases, incorrect
types and out-of-bounds dimensions are rejected. These examples additionally
require a nonempty ASCII `user_agent` or `navigator.userAgent`. They do not
extract a profile from HTML or invent browser fingerprint values.

Use `--impersonate` to select a supported `curl_cffi` browser target compatible
with that profile. The default is `chrome`; match your Chrome version and
platform to the installed transport's supported impersonation targets. Supplying
a User-Agent alone does not make an arbitrary profile compatible with a TLS
fingerprint. No profile or proprietary script fixture is bundled here.

## Starbucks: inspect generated headers

```bash
python -m examples.starbucks_headers \
  --profile /absolute/path/to/owned-profile.json \
  --script-url 'https://your-authorized-script-host.example/full-script.js'
```

Replace the example script URL with the selected URL for the Starbucks source
page. This command downloads `https://www.starbucks.com/account/signin` and your
selected scripts, calls `Client(api_key=...).generate(shape)`, and prints the
returned headers. It makes network requests and may incur a generation charge.

The generation context is exactly a `POST` to
`https://www.starbucks.com/apiproxy/v1/gift/card/check-balance` with content type
`application/json` and this dummy string body:

```json
{"cardNumber":"0000000000000000","pin":"00000000"}
```

The example never sends the gift-card request. Its output is only an inspection
of generated headers. Treat those headers as transient credentials.

## Southwest: prepare and send a username check

```bash
python -m examples.southwest_username --username dummy_user_123
```

The default prepares the example offline. To enable collection, generation and
the application POST, configure `SOUTHWEST_API_KEY` and applicable
`SOUTHWEST_APP_ID`, `SOUTHWEST_APP_VERSION`, `SOUTHWEST_CHANNEL_ID` and
`SOUTHWEST_USER_EXPERIENCE_ID` from your authorized integration. These are
application prerequisites, separate from `RAYON_API_KEY`. Missing required keys
fail before material downloads or generation.

```bash
python -m examples.southwest_username --username dummy_user_123 --send \
  --profile /absolute/path/to/owned-profile.json \
  --script-url 'https://your-authorized-script-host.example/full-script.js'
```

Replace the example script URL with the selected URL for the Southwest source
page; repeat the flag for additional scripts. The body is serialized once as a
UTF-8 string. Generation receives that exact URL, method, content type and body;
the target receives the same body bytes plus its application headers and the
returned telemetry. Required application headers are preserved. The RayonAPI
key is sent only through the SDK to RayonAPI.

One persistent `curl_cffi` session fetches the page, downloads selected scripts,
and sends the optional application request. The library's current cookie jar
retains domain, path, Secure, HttpOnly, expiry and host-only metadata. Cookies
are not synthesized from an API response or copied into request headers. This
HTTP client does not execute JavaScript or export `document.cookie`; integrations
that need browser-created cookies or document-cookie input must obtain them from
their own browser session. The final application request is restricted to the
source page's exact HTTPS origin. Every target fetch and application request
disables redirects and verifies TLS certificates; supply final URLs directly.

Set `RAYON_TARGET_PROXY` explicitly if your target session needs a proxy. Keep
its egress sticky across page, script and application requests. Ambient proxy
environment variables are disabled. The SDK has a separate ordinary TLS session
for RayonAPI, with no target proxy or target-cookie sharing. It can reuse cached
material references on repeated `generate` calls; each call still generates fresh
headers for the supplied request/profile context. These one-shot examples close
both sessions on success or failure.

Generated headers do not guarantee acceptance by Starbucks or Southwest. Target
acceptance also depends on current scripts, session cookies, profile/TLS
compatibility, egress and the application's own credentials and request rules.
Validate the full flow in your authorized integration.

## Development

```bash
pip install -r requirements.txt 'pytest>=8,<10'
pytest
```

For the unpublished SDK source, use the local-checkout installation above and
keep `PYTHONPATH` scoped to the test command if preferred. Tests use local doubles
and the library cookie jar; they never call target websites or the RayonAPI
service. See the [documentation](https://rayon-api.github.io/docs/) for the API
contract and [MIT license](LICENSE) for the examples.
