import base64
import json
import struct
import zlib
from types import SimpleNamespace

import pytest
from curl_cffi.requests import Cookies


@pytest.fixture
def canvas_data_url():
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    )
    png += chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff")) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode()


@pytest.fixture
def profile_file(tmp_path):
    path = tmp_path / "owned-profile.json"
    path.write_text(
        json.dumps({"user_agent": "Owned Chrome browser", "language": "en-GB"})
    )
    return path


@pytest.fixture
def transport():
    state = {"sessions": [], "clients": [], "shapes": [], "preparations": [], "events": []}

    class Session:
        def __init__(self, **options):
            self.options = options
            self.calls = []
            self.cookies = Cookies(options.get("cookies"))
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
                    domain="shop.example.com",
                    path="/api",
                    secure=True,
                )
            return SimpleNamespace(
                status_code=state.get("status", 200),
                headers=state.get("response_headers", {}),
                text=state.get("source", "/* full source: " + url + " */\n"),
                content=state.get("contents", {}).get(
                    url,
                    state.get("source", "/* full source: " + url + " */\n").encode(),
                ),
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

        def prepare_and_wait(self, shape, *, wait_timeout=60):
            state["preparations"].append(shape)
            state["events"].append(("prepare_and_wait", None))
            return SimpleNamespace(preparation_id="prep_0123456789abcdef", material_ref="ref_0123456789abcdef",
                state="ready", execution_backend="rust")

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


def preparation_frame():
    ident = "prep_0123456789abcdef"
    return dict(preparation_id=ident, state="ready", status_url="/v1/materials/preparations/"+ident,
        retry_after_ms=0, preparation_expires_at="2099-01-01T00:00:00Z",
        material_ref="ref_0123456789abcdef", material_expires_at="2099-01-01T00:00:00Z",
        ready_until="2099-01-01T00:00:00Z", execution_backend="rust", error=None)
