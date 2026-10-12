import json
from types import SimpleNamespace

import pytest
from curl_cffi.requests import Cookies


@pytest.fixture
def profile_file(tmp_path):
    path = tmp_path / "owned-profile.json"
    path.write_text(
        json.dumps({"user_agent": "Owned Chrome browser", "language": "en-GB"})
    )
    return path


@pytest.fixture
def transport():
    state = {"sessions": [], "clients": [], "shapes": [], "events": []}

    class Session:
        def __init__(self, **options):
            self.options = options
            self.calls = []
            self.cookies = Cookies()
            self.closed = False
            state["sessions"].append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def request(self, method, url, **options):
            self.calls.append((method, url, options))
            state["events"].append((method, url))
            if state.get("target_error"):
                raise RuntimeError("target failure")
            if method == "GET":
                # Real library jar preserves cookie scope; no cookie export from API.
                self.cookies.set(
                    "session",
                    "fresh",
                    domain="www.southwest.com",
                    path="/api",
                    secure=True,
                )
            return SimpleNamespace(
                status_code=state.get("status", 200),
                text="/* full source: " + url + " */\n",
            )

    class Client:
        def __init__(self, *, api_key):
            self.key = api_key
            self.closed = False
            state["clients"].append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def generate(self, shape):
            state["shapes"].append(shape)
            state["events"].append(("generate", None))
            if state.get("api_error"):
                raise RuntimeError("API failure")
            return SimpleNamespace(
                headers=state.get("headers", {"X-Owned-a": "generated"}),
                profile_used=state.get("profile_used", shape["profile"]),
                request_id="req-example",
                generation_ms=1,
                material_ref="reference",
                material_expires_at=None,
            )

    state.update(session_factory=Session, client_factory=Client)
    return state
