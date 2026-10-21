"""Validate offline, or explicitly fetch material, generate, and send an exact request."""

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
    load_json,
    load_profile,
    validate_inputs,
)


def load_config(path):
    config = load_json(path)
    strings = {
        "source_url", "request_url", "method", "profile", "impersonate",
        "document_cookie_file", "content_type", "body_file", "cookies_file",
        "headers_file", "mode",
    }
    arrays = {"script_urls", "allow_request_origins"}
    if not isinstance(config, dict) or not config.keys() <= strings | arrays | {"form"}:
        raise WorkflowInputError(
            "Config must be a JSON object with documented input keys; network flags and API keys belong outside config"
        )
    if any(not isinstance(config[key], str) or not config[key] for key in config.keys() & strings):
        raise WorkflowInputError("Config string inputs must be nonempty strings")
    if any(not isinstance(config[key], list) or any(not isinstance(value, str) for value in config[key])
           for key in config.keys() & arrays):
        raise WorkflowInputError("Config script_urls and allow_request_origins must be arrays of HTTPS URLs")
    if "form" in config and (not isinstance(config["form"], dict) or not config["form"].keys() <= {"id", "name"}):
        raise WorkflowInputError("Config form accepts only id and name")
    for key in {"profile", "document_cookie_file", "body_file", "cookies_file", "headers_file"} & config.keys():
        config[key] = str(Path(path).resolve().parent / config[key])
    return config


def resolve_arguments(args):
    config = load_config(args.config) if args.config else {}
    config["script_url"] = config.pop("script_urls", [])
    config["allow_request_origin"] = config.pop("allow_request_origins", [])
    values = {"content_type": None, "body_file": None, "cookies_file": None,
              "document_cookie_file": None, "headers_file": None, "mode": "header", **config}
    values.update({key: value for key, value in vars(args).items() if value is not None})
    for field in ("source_url", "request_url", "method", "profile", "impersonate"):
        if not values.get(field):
            raise WorkflowInputError("Supply source_url, request_url, method, profile and impersonate via --config or CLI flags; run --help")
    if args.form_id is not None or args.form_name is not None:
        values["form"] = dict(values.get("form", {}))
        for name in ("id", "name"):
            value = getattr(args, "form_" + name)
            if value is not None:
                values["form"][name] = value
    return argparse.Namespace(**values)


class WorkflowArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise WorkflowInputError(
            "Invalid or missing CLI arguments; run --help to check required flags and allowed methods"
        )


def main(argv=None, *, client_factory=None, session_factory=None):
    parser = WorkflowArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Workflow JSON; file paths resolve relative to this file, explicit flags override inputs")
    parser.add_argument(
        "--source-url", help="Full HTTPS page URL (SOURCE_URL)"
    )
    parser.add_argument(
        "--request-url",
        help="Exact HTTPS application endpoint (REQUEST_URL)",
    )
    parser.add_argument(
        "--allow-request-origin",
        action="append",
        help="Explicit additional HTTPS application origin (no path); repeat as needed",
    )
    parser.add_argument(
        "--method",
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
        "--profile", help="Measured browser profile JSON"
    )
    parser.add_argument(
        "--script-url",
        action="append",
        help="Explicit full protection JavaScript URL; repeat in execution order",
    )
    parser.add_argument(
        "--impersonate",
        help="curl_cffi browser target compatible with the measured profile",
    )
    parser.add_argument(
        "--cookies-file", help="Current client cookies in scoped Netscape format"
    )
    parser.add_argument(
        "--document-cookie-file",
        help="Current browser document.cookie as UTF-8; omit for an empty string",
    )
    parser.add_argument(
        "--headers-file",
        help="Application headers JSON; credentials stay local until --send",
    )
    parser.add_argument("--mode", choices=["header", "form"], help="Generation mode; defaults to header")
    parser.add_argument("--form-id", help="Optional original HTML form id for form mode")
    parser.add_argument("--form-name", help="Optional original HTML form name for form mode")
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
    args = resolve_arguments(parser.parse_args(argv))
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
        document_cookie = (Path(args.document_cookie_file).read_bytes().decode("utf-8")
                           if args.document_cookie_file else "")
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
        mode=args.mode,
        form=getattr(args, "form", None),
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
        mode=args.mode,
        form=getattr(args, "form", None),
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
            # SDK 1.1.4 accepts reason/action only from its bundled error catalog.
            if error.reason and error.action and not (key and (key in error.reason or key in error.action)):
                message += f" reason: {error.reason}. {error.action}"
            if error.billing_status in {"not_charged", "pending", "unknown"}:
                message += f" billing: {error.billing_status}."
        stage = getattr(error, "_workflow_stage", None)
        if stage == "collection":
            message += " Material collection failed; generation and the application request were not sent."
        elif stage == "application":
            message += " Application send failed after generation; acceptance is unknown. Check the application outcome and API request history before generating again."
        elif stage == "generation":
            message += " Failed during generation; the application request was not sent."
            if not isinstance(error, RayonError) or not error.action or error.billing_status != "not_charged":
                message += " Check request history before sending another request."
        raise SystemExit(message) from None


if __name__ == "__main__":
    cli()
