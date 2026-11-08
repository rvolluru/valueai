"""Host-only checks: workflow guardrails and packaged test completeness."""
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/devicefarm'))
spec = importlib.util.spec_from_file_location('android_workflows', ROOT / 'tests/devicefarm/tests/test_android_workflows.py')
workflows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflows)


def recipe():
    return {'reviewed_by': 'QA', 'fixture_ids': ['disposable'],
            'steps': [{'action': 'tap', 'label': 'Test'}],
            'verify': [{'action': 'wait', 'label': 'Saved'}],
            'cleanup': [{'action': 'back'}]}


def test_financial_recipe_requires_provider_verification():
    with pytest.raises(AssertionError, match='Sandbox'):
        workflows.validate(recipe(), financial=True)
    r = recipe(); r.update(sandbox_verified_by='QA', sandbox_environment='staging-test-mode')
    workflows.validate(r, financial=True)


def test_workflow_requires_observable_verification_and_cleanup():
    r = recipe(); r['verify'] = [{'action': 'tap', 'label': 'Test'}]
    with pytest.raises(AssertionError, match='observable'):
        workflows.validate(r)
    r = recipe(); r['cleanup'] = []
    with pytest.raises(AssertionError, match='cleanup'):
        workflows.validate(r)


def test_unknown_action_cannot_be_executed():
    r = recipe(); r['steps'] = [{'action': 'shell', 'value': 'anything'}]
    with pytest.raises(AssertionError):
        workflows.validate(r)


def test_package_contains_helpers_and_no_credentials(tmp_path):
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'), '--output', str(tmp_path)], check=True, capture_output=True)
    with zipfile.ZipFile(tmp_path / 'android_smoke.zip') as z:
        names = set(z.namelist())
        assert {'android_ui.py', 'tests/conftest.py', 'tests/test_android_regression.py',
                'tests/test_android_workflows.py', 'run_remote.py'} <= names
        assert not any('.env' in n or 'secret' in n.lower() for n in names)
    assert 'JOUFT_TEST_SCENARIO=android_smoke' in (tmp_path / 'android_smoke-spec.yml').read_text()


def test_packager_rejects_literal_credentials(tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'environment': 'staging', 'reviewed_by': 'QA', 'verified_build': '4', 'password': 'not-a-real-password'}))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'), '--manifest', str(manifest), '--output', str(tmp_path / 'out')], capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path / 'out/android_smoke.zip').exists()


def test_packager_rejects_secret_in_input_value(tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'environment': 'staging', 'reviewed_by': 'QA',
        'verified_build': '4', 'steps': [{'action': 'input', 'label': 'Password', 'value': 'not-a-real-password'}]}))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'),
        '--manifest', str(manifest), '--output', str(tmp_path / 'out')], capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path / 'out/android_smoke.zip').exists()
