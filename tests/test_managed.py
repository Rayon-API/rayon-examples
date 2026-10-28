import json
from types import SimpleNamespace
import pytest
from examples import managed

def test_managed_example_is_offline_until_explicit_and_does_not_prepare(tmp_path, monkeypatch, capsys):
    shape = {"source_url":"https://shop.example.com/", "profile":{}, "request":{"url":"https://shop.example.com/action","method":"POST","content_type":"application/json","body":" {}\n"}}
    file = tmp_path / "shape.json"; file.write_text(json.dumps(shape))
    calls=[]
    class Client:
        def __init__(self, key): assert key == "fixture-key"
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate(self, body):
            calls.append(body)
            return SimpleNamespace(request_id="req-managed", fallback_reason="unknown_material", headers={"X-Test-a":"private-telemetry"})
    managed.main(["--shape",str(file)],client_factory=Client)
    assert not calls
    monkeypatch.setenv("RAYON_API_KEY","fixture-key")
    managed.main(["--shape",str(file),"--generate"],client_factory=Client)
    assert calls == [shape]
    output=capsys.readouterr().out
    assert "fallback was used" in output and "req-managed" in output
    assert "private-telemetry" not in output and "fixture-key" not in output

@pytest.mark.parametrize("extra", [{"scripts":[]},{"material_ref":None},{"mode":"form"}])
def test_managed_example_rejects_material_before_network(tmp_path, extra):
    file=tmp_path/"shape.json";file.write_text(json.dumps({"source_url":"https://shop.example.com/","profile":{},"request":{},**extra}))
    with pytest.raises(SystemExit): managed.main(["--shape",str(file),"--generate"])
