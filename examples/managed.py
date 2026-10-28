"""Managed header generation. No target request is sent."""
import argparse
import json
import os
from pathlib import Path
from rayon_sdk_py import Client, RayonError, validate_profile


def main(argv=None, *, client_factory=Client):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape", required=True, help="UTF-8 JSON with source_url, profile and request")
    parser.add_argument("--generate", action="store_true", help="Call the API; can consume one generation credit")
    args = parser.parse_args(argv)
    try:
        shape = json.loads(Path(args.shape).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise SystemExit("Cannot read the request file; provide valid UTF-8 JSON.") from None
    if (not isinstance(shape, dict) or not {"source_url", "profile", "request"} <= shape.keys()
            or not shape.keys() <= {"source_url", "profile", "request", "document_cookie", "mode"}
            or shape.get("mode", "header") != "header"):
        raise SystemExit("Managed header input needs source_url, profile and request; omit material.")
    validate_profile(shape["profile"])
    if not args.generate:
        print("Request file loaded. Add --generate to call the API. Full input validation occurs in the SDK.")
        return
    key = os.environ.get("RAYON_API_KEY")
    if not key:
        raise SystemExit("Set RAYON_API_KEY.")
    with client_factory(key) as client:
        result = client.generate(shape)
        print("Generation request ID:", result.request_id)
        if result.fallback_reason:
            print("A fallback was used. Contact support with this request ID about the mapping issue.")
        # Apply result.headers unchanged with your target client; this example does not send them.
        return result


def cli(argv=None):
    try:
        return main(argv)
    except RayonError as error:
        # Do not print raw transport responses, inputs or credentials.
        print("API request failed. Check the dashboard request history before retrying.")
        if error.request_id:
            print("Request ID:", error.request_id)
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli()
