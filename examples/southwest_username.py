"""Prepare an exact-origin username POST; require --send for network activity."""

import argparse
import json
import os

from examples.common import (
    add_material_arguments,
    api_key,
    generate_material,
    material_profile,
)

SOURCE_URL = "https://www.southwest.com/"
ENDPOINT = "https://www.southwest.com/api/security/v4/security/username-availability"
APPLICATION_ENV = {
    "x-api-key": "SOUTHWEST_API_KEY",
    "x-app-id": "SOUTHWEST_APP_ID",
    "x-app-version": "SOUTHWEST_APP_VERSION",
    "x-channel-id": "SOUTHWEST_CHANNEL_ID",
    "x-user-experience-id": "SOUTHWEST_USER_EXPERIENCE_ID",
}


def main(argv=None, *, client_factory=None, session_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_material_arguments(parser)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Collect material, call /v1/shape, and send the application POST",
    )
    parser.add_argument("--username", default="dummy_user_123")
    args = parser.parse_args(argv)
    if not args.send:
        print(
            "Prepared POST username check. Add --send, --profile and --script-url to generate and send it."
        )
        return
    api_key()
    if not os.environ.get("SOUTHWEST_API_KEY"):
        raise ValueError("Set SOUTHWEST_API_KEY for the application request")
    profile = material_profile(args)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": SOURCE_URL.rstrip("/"),
        "Referer": SOURCE_URL,
    }
    headers.update(
        {
            name: os.environ[variable]
            for name, variable in APPLICATION_ENV.items()
            if os.environ.get(variable)
        }
    )
    body = json.dumps(
        {"username": args.username}, separators=(",", ":"), ensure_ascii=False
    )
    _, response = generate_material(
        SOURCE_URL,
        args.script_url,
        profile,
        {
            "url": ENDPOINT,
            "method": "POST",
            "content_type": "application/json",
            "body": body,
        },
        headers,
        send=True,
        client_factory=client_factory,
        session_factory=session_factory,
        impersonate=args.impersonate,
    )
    print(f"Application response: HTTP {response.status_code}")


if __name__ == "__main__":
    main()
