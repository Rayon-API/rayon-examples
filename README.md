# RayonAPI examples

Client-owned material preparation and target sessions using the published Python SDK.
RayonAPI generates six site-specific headers through `POST /v1/shape`; it returns no target cookies.
Python 3.10+ is required. Keep API keys and session data outside Git and shared logs.

[Documentation](https://docs.rayonapi.com/) · [SDK releases](https://github.com/Rayon-API/rayon-sdk-py/releases)

## Install

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

This installs `rayon-sdk-py>=1.0,<2` and `curl_cffi`.
Set `RAYON_API_KEY` in your environment; your account must have access to the requested target.

## Prepare your inputs

Save your client-owned browser profile as a strict JSON object in `owned-profile.json`.
Use supported SDK fields and a nonempty `user_agent` or `navigator.userAgent`.
Choose an available `curl_cffi` impersonation target compatible with that profile.
A User-Agent alone does not establish profile/TLS compatibility.

Select the full HTTPS URLs of the protection scripts from your authorized browser integration.
Pass `--script-url` once per script, in execution order; source is sent in full to the API.
The examples download only the chosen page and explicit scripts. They do not discover protection scripts.
See [material preparation](https://docs.rayonapi.com/material) and [profiles and sessions](https://docs.rayonapi.com/profiles-and-sessions).

## Generate and inspect headers

```sh
python -m examples.starbucks_headers \
  --profile /absolute/path/to/owned-profile.json \
  --script-url 'https://your-authorized-script-host.example/full-script.js'
```

Replace the script URL with your selected URL for the Starbucks sign-in page.
The command downloads the page and scripts, calls `Client.generate(shape)` and prints sensitive headers.
It supplies a dummy gift-card request context for generation and never sends that application request.
The generation may consume account credit; no automatic retry is performed.

The Southwest example prepares a username check offline by default.
Its `--send` option requires your authorized application's `SOUTHWEST_API_KEY` and profile/scripts.
Run `python -m examples.southwest_username --help` for its flags and application requirements.

Target sessions own their cookie jars and verify TLS. Redirects and ambient proxies are disabled.
Set `RAYON_TARGET_PROXY` explicitly if needed; keep the target session's egress consistent.
The HTTP client does not execute JavaScript or export browser-created document cookies.
Generation does not guarantee target acceptance. Validate the complete flow in your authorized integration.

## Development

Install `pytest` and run `python -m pytest`. Tests use local doubles; they never contact target sites or RayonAPI.
To test SDK changes locally, install the SDK checkout with `python -m pip install -e /absolute/path/to/rayon-sdk-py`.

[API reference](https://docs.rayonapi.com/api-reference) · [Support](mailto:support@rayonapi.com) · [Discord](https://discord.gg/TwhkJNyHWs) · [MIT license](LICENSE)
