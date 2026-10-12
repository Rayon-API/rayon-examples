"""Show an exact-origin application POST using generated telemetry."""

import argparse
import json
import os

from examples.common import api_key, replay_once

SOURCE_URL = "https://www.southwest.com/"
ENDPOINT = "https://www.southwest.com/api/security/v4/security/username-availability"
APPLICATION_ENV = {
    "x-api-key": "SOUTHWEST_API_KEY",
    "x-app-id": "SOUTHWEST_APP_ID",
    "x-app-version": "SOUTHWEST_APP_VERSION",
    "x-channel-id": "SOUTHWEST_CHANNEL_ID",
    "x-user-experience-id": "SOUTHWEST_USER_EXPERIENCE_ID",
}


def main(argv=None, *, solver=None, replay=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send", action="store_true", help="Call /solve and send the application POST"
    )
    parser.add_argument("--username", default="dummy_user_123")
    args = parser.parse_args(argv)
    if not args.send:
        print("Prepared POST username check. Add --send to call /solve and send it.")
        return
    key = api_key()
    if not os.environ.get("SOUTHWEST_API_KEY"):
        raise ValueError("Set SOUTHWEST_API_KEY for the application request")
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
    if solver is None:
        from rayon_sdk_py import solve

        solver = solve
    result = solver(SOURCE_URL, key)
    body = json.dumps({"username": args.username}, separators=(",", ":"))
    response = (replay or replay_once)(
        result, SOURCE_URL, ENDPOINT, "POST", body, headers
    )
    print(f"Application response: HTTP {response.status_code}")


if __name__ == "__main__":
    main()
