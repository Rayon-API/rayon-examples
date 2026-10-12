"""Capture and print the six telemetry headers; no gift-card request is sent."""

import json

from examples.common import api_key

SOURCE_URL = "https://www.starbucks.com/account/signin"


def main(*, solver=None):
    if solver is None:
        from rayon_sdk_py import solve

        solver = solve
    result = solver(SOURCE_URL, api_key())
    print(json.dumps(result.headers, indent=2))


if __name__ == "__main__":
    main()
