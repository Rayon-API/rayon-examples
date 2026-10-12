"""Collect selected material and print generated headers; no gift-card request is sent."""

import argparse
import json

from examples.common import (
    add_material_arguments,
    api_key,
    generate_material,
    material_profile,
)

SOURCE_URL = "https://www.starbucks.com/account/signin"
ENDPOINT = "https://www.starbucks.com/apiproxy/v1/gift/card/check-balance"


def main(argv=None, *, client_factory=None, session_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_material_arguments(parser)
    args = parser.parse_args(argv)
    api_key()
    profile = material_profile(args)
    # Dummy string body establishes the exact generation context, never a live balance check.
    body = '{"cardNumber":"0000000000000000","pin":"00000000"}'
    result, _ = generate_material(
        SOURCE_URL,
        args.script_url,
        profile,
        {
            "url": ENDPOINT,
            "method": "POST",
            "content_type": "application/json",
            "body": body,
        },
        {},
        client_factory=client_factory,
        session_factory=session_factory,
        impersonate=args.impersonate,
    )
    print(json.dumps(result.headers, indent=2))


if __name__ == "__main__":
    main()
