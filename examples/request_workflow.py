"""Validate offline, or explicitly fetch material, generate headers, and send an exact request."""

import argparse
import os
import re
from pathlib import Path

from rayon_sdk_py import RayonError

from examples.common import (
    WorkflowInputError,
    generate_material,
    load_cookies,
    load_headers,
    load_profile,
    validate_inputs,
)


class WorkflowArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise WorkflowInputError(
            "Invalid or missing CLI arguments; run --help to check required flags and allowed methods"
        )


def main(argv=None, *, client_factory=None, session_factory=None):
    parser = WorkflowArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url", required=True, help="Full HTTPS page URL (SOURCE_URL)"
    )
    parser.add_argument(
        "--request-url",
        required=True,
        help="Exact HTTPS application endpoint (REQUEST_URL)",
    )
    parser.add_argument(
        "--allow-request-origin",
        action="append",
        default=[],
        help="Explicit additional HTTPS application origin (no path); repeat as needed",
    )
    parser.add_argument(
        "--method",
        required=True,
        choices=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    parser.add_argument(
        "--content-type", help="Exact application Content-Type; required for a body"
    )
    parser.add_argument(
        "--body-file",
        help="UTF-8 request body; bytes are preserved, including newlines",
    )
    parser.add_argument(
        "--profile", required=True, help="Measured browser profile JSON"
    )
    parser.add_argument(
        "--script-url",
        action="append",
        required=True,
        help="Explicit full protection JavaScript URL; repeat in execution order",
    )
    parser.add_argument(
        "--impersonate",
        required=True,
        help="curl_cffi browser target compatible with the measured profile",
    )
    parser.add_argument(
        "--cookies-file", help="Current client cookies in scoped Netscape format"
    )
    parser.add_argument(
        "--document-cookie-file",
        required=True,
        help="Current browser document.cookie as UTF-8; use an empty file if empty",
    )
    parser.add_argument(
        "--headers-file",
        help="Application headers JSON; credentials stay local until --send",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fetch-and-generate",
        action="store_true",
        help="Fetch source page and chosen scripts, call /v1/shape; no application request",
    )
    mode.add_argument(
        "--send",
        action="store_true",
        help="Fetch source page and chosen scripts, generate, then send the exact application request in the same session",
    )
    args = parser.parse_args(argv)
    profile = load_profile(args.profile)
    try:
        body = (
            Path(args.body_file).read_bytes().decode("utf-8")
            if args.body_file
            else None
        )
    except (OSError, UnicodeError):
        raise WorkflowInputError(
            "Cannot read --body-file; provide a readable UTF-8 text body"
        ) from None
    request = {
        "url": args.request_url,
        "method": args.method,
        "content_type": args.content_type,
        "body": body,
    }
    try:
        document_cookie = Path(args.document_cookie_file).read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        raise WorkflowInputError(
            "Cannot read --document-cookie-file; provide a readable UTF-8 browser cookie snapshot"
        ) from None
    headers = load_headers(args.headers_file) if args.headers_file else {}
    cookies = load_cookies(args.cookies_file) if args.cookies_file else None
    validate_inputs(
        args.source_url,
        args.script_url,
        profile,
        request,
        headers,
        document_cookie,
        allow_request_origins=args.allow_request_origin,
    )
    if not args.send and not args.fetch_and_generate:
        print(
            "Inputs validated offline. Add --fetch-and-generate or --send to run the workflow."
        )
        return
    result, response = generate_material(
        args.source_url,
        args.script_url,
        profile,
        request,
        headers,
        document_cookie=document_cookie,
        cookies=cookies,
        send=args.send,
        client_factory=client_factory,
        session_factory=session_factory,
        impersonate=args.impersonate,
        allow_request_origins=args.allow_request_origin,
    )
    print(f"Generation request ID: {result.request_id}")
    if response is not None:
        print(f"Application response: HTTP {response.status_code}")


def cli(argv=None, **factories):
    try:
        return main(argv, **factories)
    except WorkflowInputError as error:
        raise SystemExit(f"Input error: {error}") from None
    except Exception as error:
        # Only SDK metadata passes this boundary; never format transport exception text.
        message = (
            f"Workflow failed ({type(error).__name__}); check session configuration."
        )
        if isinstance(error, RayonError):
            key = os.environ.get("RAYON_API_KEY")
            for label, value, pattern in (
                ("code", error.code, r"[a-z][a-z0-9_]{0,63}"),
                ("request ID", error.request_id, r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"),
            ):
                if (
                    isinstance(value, str)
                    and re.fullmatch(pattern, value)
                    and not (key and key in value)
                ):
                    message += f" {label}: {value}."
        raise SystemExit(message) from None


if __name__ == "__main__":
    cli()
