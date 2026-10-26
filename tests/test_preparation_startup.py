import copy
from types import SimpleNamespace
import pytest
from examples import common, request_workflow
from test_workflow import inputs, factories

ID = 'prep_0123456789abcdef'
REF = 'ref_0123456789abcdef'

def install_preparation(transport, monkeypatch, *, fail=False):
    calls = []
    def prepare_and_wait(self, shape, *, wait_timeout=60):
        calls.append(copy.deepcopy(shape))
        transport['events'].append(('prepare_and_wait', None))
        if fail:
            from rayon_sdk_py import PreparationError
            raise PreparationError('failed', ID, {'code':'preparation_failed'})
        return SimpleNamespace(preparation_id=ID, material_ref=REF, state='ready', execution_backend='rust')
    monkeypatch.setattr(transport['client_factory'], 'prepare_and_wait', prepare_and_wait, raising=False)
    return calls

def test_live_workload_prepares_exact_context_before_generation_and_target_send(tmp_path, profile_file, transport, monkeypatch):
    monkeypatch.setenv('RAYON_API_KEY', 'rayon-key')
    calls = install_preparation(transport, monkeypatch)
    request_workflow.main(inputs(tmp_path, profile_file) + ['--send'], **factories(transport))
    assert len(calls) == 1
    shape = calls[0]
    assert shape['document_cookie'] == 'visible=current'
    assert shape['request']['body'] == ' {"name":"é"}\r\n'
    assert len(shape['scripts']) == 2
    assert transport['shapes'][0]['material_ref'] == REF
    assert 'scripts' not in transport['shapes'][0]
    names = [event[0] for event in transport['events']]
    assert names.index('prepare_and_wait') < names.index('generate') < names.index('POST')

def test_prepare_failure_stops_workload_and_prints_safe_resume_id(tmp_path, profile_file, transport, monkeypatch):
    monkeypatch.setenv('RAYON_API_KEY', 'rayon-key')
    install_preparation(transport, monkeypatch, fail=True)
    with pytest.raises(SystemExit) as caught:
        request_workflow.cli(inputs(tmp_path, profile_file) + ['--send'], **factories(transport))
    assert ID in str(caught.value.code)
    assert 'preparation' in str(caught.value.code).lower()
    assert 'application request was not sent' in str(caught.value.code)
    assert not transport['shapes']
    assert all(event[0] != 'POST' for event in transport['events'])

def test_prepare_only_is_explicit_and_never_generates_or_sends(tmp_path, profile_file, transport, monkeypatch, capsys):
    monkeypatch.setenv('RAYON_API_KEY', 'rayon-key')
    calls = install_preparation(transport, monkeypatch)
    request_workflow.main(inputs(tmp_path, profile_file) + ['--prepare-only'], **factories(transport))
    assert len(calls) == 1 and not transport['shapes']
    assert 'Preparation ready' in capsys.readouterr().out
    assert all(event[0] != 'POST' for event in transport['events'])
