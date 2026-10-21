# RayonAPI examples

Start with the [SDK quickstart](https://docs.rayonapi.com/quickstart):
install an SDK, check usage for free, prepare inputs, generate, then apply the result
through your existing HTTP client or browser.

[Python](https://github.com/Rayon-API/rayon-sdk-py) ·
[JavaScript / TypeScript](https://github.com/Rayon-API/rayon-sdk-js) ·
[Documentation](https://docs.rayonapi.com/)

[Go v1.0.0](https://github.com/Rayon-API/rayon-sdk-go) is available.
[Playwright 0.1.0](https://github.com/Rayon-API/rayon-sdk-playwright) is published.

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
# Download and generate (can consume credit); do not send the target request.
python -m examples.request_workflow --config local/workflow.json --fetch-and-generate

# Download, generate and send through the same target session.
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
