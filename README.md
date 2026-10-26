# RayonAPI examples


The additive preparation API is available. These examples use SDK 2.0.0 to
prepare and wait before starting a workload. Legacy generation remains available;
mandatory preparation is not enabled. A 30-day migration window and cutoff will be
announced separately; no cutoff date is set. Rust-only enforcement remains gated
on complete-output readiness and the announced migration.

Start with the [SDK quickstart](https://docs.rayonapi.com/quickstart):
install an SDK, check usage for free, collect inputs, explicitly prepare and wait,
then generate and apply the result
through your existing HTTP client or browser.

[Python](https://github.com/Rayon-API/rayon-sdk-py) ·
[JavaScript / TypeScript](https://github.com/Rayon-API/rayon-sdk-js) ·
[Documentation](https://docs.rayonapi.com/)

[Go v2.0.0](https://github.com/Rayon-API/rayon-sdk-go) is available.
[Playwright 1.0.0](https://github.com/Rayon-API/rayon-sdk-playwright) is available.

## Optional Python helper

Use this helper when you want to download explicitly selected script URLs and
optionally send the target request through one `curl_cffi` session. If your
integration already supplies inputs and sends requests, call the SDK directly.
The helper does not launch a browser, discover scripts or measure a profile.

Requires Python 3.10+.

```sh
git clone https://github.com/Rayon-API/rayon-examples.git
cd rayon-examples
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p local
```

Save `local/workflow.json` with values from your integration. File paths resolve
relative to this config file; the example domains are placeholders.

```json
{
  "source_url": "https://shop.example.com/account",
  "request_url": "https://shop.example.com/api/check",
  "method": "POST",
  "profile": "profile.json",
  "script_urls": ["https://shop.example.com/protection.js?seed=observed"],
  "impersonate": "chrome",
  "content_type": "application/json",
  "body_file": "request-body.txt"
}
```

Use an appropriate profile and exact UTF-8 request body. `impersonate` configures
this helper's transport. Add cookies, application headers or a target proxy only
when your flow needs them. See the [input and config reference](docs/workflow.md#prepare-inputs).
Keep keys and local inputs outside Git; `local/` is ignored.

Validate offline first:

```sh
python -m examples.request_workflow --config local/workflow.json
```

Set `RAYON_API_KEY` in your environment, then explicitly choose a network action:

```sh
# Collect and prepare only; no generation or application request.
python -m examples.request_workflow --config local/workflow.json --prepare-only

# Download, prepare and wait, then generate (can consume credit); no target request.
python -m examples.request_workflow --config local/workflow.json --fetch-and-generate

# Download, prepare and wait, generate and send in the same target session.
python -m examples.request_workflow --config local/workflow.json --send
```

Config cannot enable network access. Each network command starts a new workflow;
generation-only mode does not save a session for a later send. Output contains
request IDs and target status, not cookies or generated telemetry. Generation
does not guarantee target acceptance.

For form mode, cookie scope, allowed origins, direct CLI flags, safe error handling
and offline tests, read the [workflow reference](docs/workflow.md).
For a persistent integration, keep your SDK client and any required target session
open across calls; generate fresh telemetry for each exact request.

[API reference](https://docs.rayonapi.com/api-reference) ·
[Support](mailto:support@rayonapi.com) · [MIT license](LICENSE)


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
