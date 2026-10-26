# Optional Python workflow reference


The additive preparation API is available. These examples use SDK 2.0.0 to
prepare and wait before starting a workload. Legacy generation remains available;
mandatory preparation is not enabled. A 30-day migration window and cutoff will be
announced separately; no cutoff date is set. Rust-only enforcement remains gated
on complete-output readiness and the announced migration.

An optional Python helper for client-owned material collection and `POST /v1/shape`.
Your client supplies complete protection JavaScript, profile inputs appropriate to
its flow, cookies when needed, and the exact application request context. RayonAPI
returns request headers or form telemetry; your client sends the application request.
RayonAPI never fetches target pages or scripts and returns no target cookies.

If you already have an HTTP/browser integration, call the
[Python SDK](https://github.com/Rayon-API/rayon-sdk-py) directly with material from
that session and send the result through that same integration. No browser collector
or profile generator is required by this repository. The helper below chooses
`curl_cffi` for its target transport; use it when that fits your session.

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

Dependencies are `rayon-sdk-py>=2.0.0,<3` and `curl_cffi`.
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
For this helper, save the required inputs and any needed optional inputs under
`local/`, using the browser/client session you will use:

- `profile.json`: supported profile inputs with a nonempty `user_agent` or
  `navigator.userAgent` for this helper’s transport. Include other navigator,
  screen/window, WebGL or canvas values when your flow needs them; supplied values
  must match the represented environment.
  See [profiles and sessions](https://docs.rayonapi.com/profiles-and-sessions) for the schema.
- `cookies.txt` (optional): current cookies exported in Netscape format, preserving domain,
  path, secure, and expiry scope. Omit `--cookies-file` for an empty session.
  `curl_cffi` can lose imported HttpOnly metadata during its cookie conversion;
  the HTTP jar must not be used to infer JavaScript cookie visibility.
- `document-cookie.txt` (optional): the current browser-visible `document.cookie` string,
  UTF-8 without a trailing newline. Omit this input when the string is empty.
  This differs from the HTTP cookie jar: HttpOnly cookies are not browser-visible.
- `request-body.txt` (for requests with a body): the exact UTF-8 application body, including any intended whitespace.
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

## Start with a config file

Save `local/workflow.json` using values from your own integration:

```json
{
  "source_url": "https://shop.example.com/account",
  "request_url": "https://shop.example.com/api/check",
  "method": "POST",
  "profile": "profile.json",
  "script_urls": [
    "https://shop.example.com/loader.js",
    "https://cdn.example/payload.js"
  ],
  "impersonate": "chrome",
  "content_type": "application/json",
  "body_file": "request-body.txt"
}
```

File paths in config resolve relative to the config file. Validate first; this reads
local inputs only and needs no API key:

```sh
python -m examples.request_workflow --config local/workflow.json
```

Set `RAYON_API_KEY` in your environment, then explicitly choose the next step:

```sh
# Collect and prepare only; no generation or application request.
python -m examples.request_workflow --config local/workflow.json --prepare-only

# Fetch full inputs, prepare and wait, then generate; generation can consume credit.
python -m examples.request_workflow --config local/workflow.json --fetch-and-generate

# Fetch, prepare and wait, generate, and send in one run.
python -m examples.request_workflow --config local/workflow.json --send
```

Each network command starts a new workflow and prepares its full context. Commands
that generate produce fresh telemetry. The
generation-only command does not save a result for a later send. Neither network
mode can be enabled by config; API keys are accepted only through the environment.
Unknown config keys, duplicate JSON keys, and invalid local inputs are rejected
before network activity. This checks supplied inputs, not freshness or completeness
of the selected scripts or browser measurements.

Required config keys (or equivalent CLI flags) are `source_url`, `request_url`,
`method`, `profile`, `script_urls`, and `impersonate`. Optional keys are:

| Key | Meaning / default |
| --- | --- |
| `content_type`, `body_file` | Exact content type and original UTF-8 body; omitted for a bodyless request |
| `cookies_file` | Scoped Netscape HTTP cookie export; empty session when omitted |
| `document_cookie_file` | Browser-visible cookie snapshot; empty string when omitted |
| `headers_file` | Application headers JSON; empty object when omitted |
| `allow_request_origins` | Array of additional approved HTTPS origins; empty when omitted |
| `mode` | `header` (default) or `form` |
| `form` | Optional object with only `id` and/or `name`, for form mode |

All existing flags remain available. Explicit flags override the corresponding
config values; repeated `--script-url` or `--allow-request-origin` flags replace
that config array. CLI file paths resolve from the current directory.
`--form-id` and `--form-name` override their individual form metadata fields.

## Use flags directly

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
and generate without sending the application request. Generation can consume
account credit; the helper adds no extra retries. Output contains only the generation
request ID and, when sending, the application HTTP status. Headers, cookies, and response
bodies are not printed. Local input errors show actionable guidance; transport and
SDK failures show the error class, safe API metadata, trusted reason/action, billing
status when available, and the workflow stage without raw exception text. If billing
or the application outcome is uncertain, check request history and the application
before generating again.

With `--send`, a single target session downloads the source page and all selected
scripts, then sends the exact endpoint/method/body with `result.headers` in header
mode or prefixes `result.form_body` in form mode. Its cookie
jar, browser impersonation, User-Agent, and proxy remain consistent. The SDK uses a
separate session for RayonAPI. The API omits canvas from `profile_used`; the example
compares the remaining supplied profile fields before sending, while still supplying
any supplied canvas input for generation. Application requests must share the source page's exact
HTTPS origin by default. For an application API on another approved origin, add
`--allow-request-origin https://api.shop.example.com` explicitly (repeat for each
allowed origin). Script URLs may use a different HTTPS host. The shared cookie jar
keeps URL scope; source-page cookies are never flattened into an endpoint Cookie header.

The client verifies TLS and refuses redirects. Ambient proxies are disabled.
Set `RAYON_TARGET_PROXY` explicitly when needed. This HTTP example does not execute
JavaScript or measure browser signals; export fresh profile and cookie data from your
browser integration. Keep the supplied browser-visible cookie snapshot consistent with
any cookies updated during collection. Generation does not guarantee target acceptance.

## Form mode

For an original HTML form submission, set `mode` to `form`, use `method: "POST"`,
`content_type: "application/x-www-form-urlencoded"` (optional UTF-8 charset), and
point `body_file` at the original URL-encoded application fields. Optional `form`
metadata identifies the original HTML form, for example:

```json
{
  "mode": "form",
  "form": {"id": "checkout", "name": "order"},
  "method": "POST",
  "content_type": "application/x-www-form-urlencoded",
  "body_file": "checkout-body.txt"
}
```

Merge those fields into the complete config above. The original body must precede
telemetry insertion; a complete existing telemetry family is rejected locally.
Form mode returns `form_body` and `form_fields`, with no generated `headers`.
When sending, the helper prefixes `form_body` once, followed by `&` and the original
body when nonempty. It preserves original body bytes, duplicate field names, order,
and encoding; it never converts the application fields into a dictionary.

## Reuse clients in your integration

For multiple requests, keep a single SDK `Client` (or `AsyncClient`) open inside a
context manager so API connections can be reused. Keep your own target session open
too, with consistent cookies, proxy, browser identity and profile where your flow
uses them. Generate for each
exact request context and send through that target session. The optional CLI creates
one target session and one SDK client per run; it does not persist them across runs.

## Test offline

```sh
python -m pip install 'pytest>=8,<10'
python -m pytest
```

Tests use local transport doubles and real cookie jars; they never contact targets or RayonAPI.

[API reference](https://docs.rayonapi.com/api-reference) · [Support](mailto:support@rayonapi.com) · [MIT license](../LICENSE)


## Preparation before workload

Every live mode calls `prepare_and_wait` once with the complete script sources,
profile, exact request, source-document cookies, and mode/form context before
starting generation. A ready result confirms complete validation/publication and
`execution_backend: "rust"`. Partial material or partial output fails preparation;
a downloaded script or source reference alone does not make a workload ready.

`--prepare-only` returns safe preparation metadata without generating or sending.
`--fetch-and-generate` prepares and waits, then generates without sending the
application request. `--send` prepares and waits, generates fresh output, then sends
that exact request through the same target session. These modes are mutually
exclusive and cannot be enabled from config. Running a later CLI command starts a
new workflow; the helper does not persist a target session or old generated headers.

Preparation failure stops the workload. The CLI prints a safe preparation ID when
available so an existing job can be resumed with `client.get_preparation(id)` or
`client.wait_until_ready(id, wait_timeout=60)`. Waiting/cancellation does not cancel
the server job. States are `queued`, `learning`, `validating`, `publishing`, `ready`,
`failed`, and `expired`. A failed or expired job needs corrected/current context and
an explicit new prepare, rather than an arbitrary generation retry.

For persistent integrations, reprepare after `ready_until` or relevant full-context
changes. `material_expires_at` governs the source reference and can differ from
readiness lifetime. Generation uses the returned material reference and still
produces fresh complete telemetry for every exact request. The SDK `generate`
method never prepares or waits implicitly. The preparation POST is issued once
with a stable idempotency key; only transient status GETs are retried with jitter.
See the [preparation contract](https://docs.rayonapi.com/reference/preparation).
