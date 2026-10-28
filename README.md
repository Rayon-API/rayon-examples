# Rayon examples

For supported public header flows, Rayon manages material. Send a source-page
URL, profile and exact request. No collection or preparation is needed.
Your client keeps control of the target HTTP request and session.

## Managed generation

```sh
python -m pip install 'rayon-sdk-py>=2.1.0,<3'
```

```python
import os
from rayon_sdk_py import Client

with Client(os.environ["RAYON_API_KEY"]) as client:
    result = client.generate({
        "source_url": "https://shop.example.com/account",
        "profile": {},
        "request": {
            "url": "https://shop.example.com/api/check", "method": "POST",
            "content_type": "application/json", "body": "{}",
        },
    })
    if result.fallback_reason:
        print("A fallback was used. Contact support with request ID:", result.request_id)
    # Apply every returned header with your own target client, including optional a0.
```

Replace reserved URLs with your approved supported source and endpoint. `{}` uses
default profile values; supply measured values and current JavaScript-visible
cookies when needed. Keep `scripts` and `material_ref` omitted on later automatic
calls so material updates are selected. Registered public material is maintained
by Rayon; arbitrary supplied URLs are not fetched on demand.

The runnable `examples/managed.py` reads the same object from a private JSON file:

```sh
python -m examples.managed --shape local/shape.json             # No API call.
python -m examples.managed --shape local/shape.json --generate  # Can consume credit.
```

Install the repository requirements first. The example prints request IDs and
fallback guidance, never headers, cookies or source. It does not send the target
request. Keep files under ignored `local/`. Generation does not prove target
acceptance; inspect the target response. Check history before retrying an
uncertain outcome.

## Optional explicit-material workflow

Customer uploads and private references remain supported. Form mode currently
requires explicit material. The advanced helper below intentionally collects,
prepares and generates with your own chosen sources. It is not needed for
managed header generation. Private uploads are not added to the public registry.

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



## Optional preparation

The explicit workflow checks readiness before generation. Preparation needs
explicit material; usable validated mappings with defaulted internal records can
be ready. Required output validation remains unchanged. `--prepare-only` never
generates or sends the application request. Wait timeout/cancellation leaves the
server job running; use its preparation ID to resume status reads.

[Quickstart](https://docs.rayonapi.com/quickstart) ·
[Workflow reference](docs/workflow.md) · [Preparation](https://docs.rayonapi.com/api-reference)
