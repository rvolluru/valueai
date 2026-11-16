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


def test_all_21_workflows_have_concrete_implementations():
    assert len(workflows.WORKFLOWS) == 21
    assert set(workflows.FUNCTIONS) == set(workflows.REQUIRED) == set(workflows.WORKFLOWS)
    assert all(callable(f) and f.__name__ == name for name, f in workflows.FUNCTIONS.items())


def test_financial_workflow_refuses_live_or_unpinned_sandbox(monkeypatch):
    monkeypatch.setenv('JOUFT_TEST_API_TOKEN_A', 'unread-test-token')
    monkeypatch.setenv('JOUFT_TEST_SANDBOX_CONFIRMED', '1')
    manifest = {'exclusive_accounts': True, 'verified_build': 'build1',
        'workflows': {'subscription_change_cancel': dict(disposable=True, plan_label='Gold', plan_key='gold', amount_label='$10')},
        'sandbox': dict(verified_by='QA', verified_build='old-build', stripe_mode='test', shippo_mode='test')}
    with pytest.raises(AssertionError, match='match this build'):
        workflows.prerequisites('subscription_change_cancel', manifest)
    manifest['sandbox']['verified_build'] = 'build1'
    manifest['sandbox']['shippo_mode'] = 'live'
    with pytest.raises(AssertionError, match='test mode'):
        workflows.prerequisites('subscription_change_cancel', manifest)
    manifest['sandbox']['shippo_mode'] = 'test'
    workflows.prerequisites('subscription_change_cancel', manifest)


def test_workflows_reject_arbitrary_recipes(monkeypatch):
    monkeypatch.setenv('JOUFT_TEST_API_TOKEN_A', 'not-used')
    manifest = {'exclusive_accounts': True, 'workflows': {'like_restore': dict(title='Fixture', disposable=True, steps=[{'action': 'shell'}])}}
    with pytest.raises(AssertionError, match='not recipes'):
        workflows.prerequisites('like_restore', manifest)


def test_package_contains_helpers_and_no_credentials(tmp_path):
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'), '--output', str(tmp_path)], check=True, capture_output=True)
    with zipfile.ZipFile(tmp_path / 'android_smoke.zip') as z:
        names = set(z.namelist())
        assert {'android_ui.py', 'android_workflow_support.py', 'tests/conftest.py', 'tests/test_android_regression.py',
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


from android_workflow_support import API, Controls, offline, permission, verify_staging_apk
import android_workflow_support as support
import base64
import hashlib
import time


def staged_apk(tmp_path, environment='staging', origin='https://staging.jouft.com'):
    path = tmp_path / 'fixture.apk'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('assets/app.config', json.dumps({'android': {'package': 'com.jouft.app.dev'},
            'extra': {'appEnvironment': environment, 'apiBaseUrl': origin}}))
    return path, dict(environment='staging', reviewed_by='QA', verified_build='build',
        apk_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), api_origin='https://staging.jouft.com')


def test_workflows_accept_verified_staging_apk(tmp_path):
    path, manifest = staged_apk(tmp_path)
    verify_staging_apk(manifest, path)


@pytest.mark.parametrize('environment,origin', [('production', 'https://api.jouft.com'), ('staging', 'https://api.jouft.com')])
def test_dev_identity_does_not_authorize_production_mutation(tmp_path, environment, origin):
    path, manifest = staged_apk(tmp_path, environment, origin)
    with pytest.raises(AssertionError):
        verify_staging_apk(manifest, path)


def test_apk_digest_pins_exact_binary(tmp_path):
    path, manifest = staged_apk(tmp_path)
    manifest['apk_sha256'] = '0' * 64
    with pytest.raises(AssertionError, match='digest'):
        verify_staging_apk(manifest, path)


@pytest.mark.parametrize('origin', ['https://api.jouft.com', 'https://staging.jouft.com.evil.invalid', 'http://staging.jouft.com'])
def test_observer_cannot_target_other_origin(origin):
    with pytest.raises(AssertionError):
        API(origin)


def jwt(subject, expiry):
    payload = base64.urlsafe_b64encode(json.dumps({'sub': subject, 'exp': expiry}).encode()).decode().rstrip('=')
    return 'header.' + payload + '.signature'


def test_observer_identity_and_expiration_checked_before_request(monkeypatch):
    monkeypatch.setenv('JOUFT_TEST_API_TOKEN_A', jwt('wrong-user', time.time() + 60))
    with pytest.raises(AssertionError, match='account mismatch'):
        API('https://staging.jouft.com', subject='fixture-A').token()
    monkeypatch.setenv('JOUFT_TEST_API_TOKEN_A', jwt('fixture-A', 1))
    with pytest.raises(pytest.skip.Exception, match='expired'):
        API('https://staging.jouft.com', subject='fixture-A').token()


def test_observer_renewal_rejects_live_auth_secret(monkeypatch):
    monkeypatch.setenv('JOUFT_TEST_CLERK_SESSION_A', 'sess_fixture')
    monkeypatch.setenv('JOUFT_TEST_CLERK_SECRET', 'sk_live_not-a-real-key')
    with pytest.raises(AssertionError, match='test instance'):
        API('https://staging.jouft.com', subject='fixture-A').token()


def test_cleanup_continues_after_failure_and_records_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVICEFARM_LOG_DIR', str(tmp_path))
    case = object.__new__(workflows.Case)
    case.name = 'cleanup-test'
    completed = []
    def fail():
        raise RuntimeError('sensitive details must not be recorded')
    case.cleanups = [lambda: completed.append('restored'), fail]
    with pytest.raises(AssertionError, match='cleanup failed'):
        case.close()
    assert completed == ['restored']
    record = (tmp_path / 'cases/cleanup-test-cleanup.json').read_text()
    assert json.loads(record)['failures'] == 1
    assert 'sensitive' not in record


def test_network_radios_restored_independently_after_failure(monkeypatch):
    commands = []
    def device(*args):
        commands.append(args)
        if args[:3] == ('shell', 'settings', 'get'):
            return '1' if args[-1] == 'wifi_on' else '0'
        return ''
    monkeypatch.setattr(support, 'adb', device)
    with pytest.raises(RuntimeError):
        with offline():
            raise RuntimeError('simulated failure')
    assert commands[-2:] == [('shell', 'svc', 'wifi', 'enable'), ('shell', 'svc', 'data', 'disable')]


def test_permission_restores_original_denied_state(monkeypatch):
    commands = []
    def device(*args):
        commands.append(args)
        return 'android.permission.CAMERA: granted=false'
    monkeypatch.setattr(support, 'adb', device)
    app = type('App', (), {'package': 'com.jouft.app.dev'})()
    with pytest.raises(RuntimeError):
        with permission(app, 'android.permission.CAMERA'):
            raise RuntimeError('simulated failure')
    assert commands[-1] == ('shell', 'pm', 'revoke', app.package, 'android.permission.CAMERA')


@pytest.mark.parametrize('field', ['api_token', 'clerk_secret', 'new_password', 'authorization'])
def test_packager_rejects_workflow_secret_fields(tmp_path, field):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'environment': 'staging', 'reviewed_by': 'QA', 'verified_build': '4', field: 'never-package-this'}))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'),
        '--manifest', str(manifest), '--output', str(tmp_path / 'out')], capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path / 'out/android_smoke.zip').exists()


def test_payment_flow_refuses_live_sheet_before_ui_action():
    class Observer:
        def get(self, path):
            return {'items': []}
        def call(self, *args):
            return {'publishable_key': 'pk_live_not-a-real-key'}
    class Screen:
        def profile(self, *args):
            pytest.fail('Live payment reached UI')
    case = object.__new__(workflows.Case)
    case.app = object(); case.c = Screen(); case.api = Observer(); case.cfg = {}; case.cleanups = []
    with pytest.raises(AssertionError, match='live Stripe'):
        workflows.payment_add_default_remove(case)


def test_stale_trade_uses_independent_account_and_cannot_accept(monkeypatch):
    from types import SimpleNamespace
    events = []
    state = {'status': 'proposed'}
    class Observer:
        def __init__(self, who): self.who = who
        def profile(self): return {'owner_subject': self.who}
        def offer(self, identity):
            return dict(status=state['status'], target_listing={'title': 'Target'}, from_subject='A', to_subject='B')
        def get(self, path): return {'shipments': []}
        def call(self, method, path, data, allowed=(200,)):
            events.append((self.who, data['status']))
            if self.who == 'B':
                state['status'] = 'declined'
            else:
                assert data['status'] == 'accepted' and allowed == (400, 409)
                assert state['status'] == 'declined'
            return {}
    class Screen:
        def offer(self, title, lane='Active'): events.append(('screen', lane))
        def relaunch(self): pass
    button = SimpleNamespace(click=lambda: events.append(('native', 'Decline')))
    case = SimpleNamespace(cfg=dict(offer_id='offer1', target_title='Target'), api=Observer('A'), other=Observer('B'),
        c=Screen(), app=SimpleNamespace(wait=lambda *a: None, elements=lambda *a: [button], has=lambda *a: False),
        labels=lambda *a: None)
    workflows.trade_stale_action(case)
    assert events.index(('screen', 'Active')) < events.index(('B', 'declined')) < events.index(('native', 'Decline'))
    assert state['status'] == 'declined'


def test_workflow_selection_rejects_unknown_cases(monkeypatch):
    monkeypatch.setenv('JOUFT_TEST_WORKFLOW_CASES', 'camera_capture,not_a_case')
    with pytest.raises(AssertionError, match='Unknown'):
        workflows.selected_workflows()


def test_workflow_example_covers_all_cases_and_contains_no_recipes():
    manifest = json.loads((ROOT / 'tests/devicefarm/android-fixtures.example.json').read_text())
    assert set(manifest['workflows']) == set(workflows.WORKFLOWS)
    for name, required in workflows.REQUIRED.items():
        assert set(required) <= set(manifest['workflows'][name])
        assert not {'steps', 'verify', 'cleanup'} & set(manifest['workflows'][name])


def test_selected_workflow_is_pinned_in_packaged_spec(tmp_path):
    manifest = tmp_path / 'data.json'
    manifest.write_text(json.dumps({'environment': 'staging', 'reviewed_by': 'QA', 'verified_build': 'build'}))
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'),
        '--scenario', 'android_workflows', '--workflow', 'camera_capture', '--manifest', str(manifest),
        '--output', str(tmp_path / 'out')], check=True, capture_output=True)
    assert 'JOUFT_TEST_WORKFLOW_CASES=camera_capture python run_remote.py' in (tmp_path / 'out/android_workflows-spec.yml').read_text()


def test_real_email_never_uses_clerk_test_code(monkeypatch):
    from android_ui import verification_code
    monkeypatch.delenv('JOUFT_TEST_SECOND_OTP_SECRET', raising=False)
    monkeypatch.setenv('JOUFT_TEST_SECOND_EMAIL', 'qa@example.invalid')
    with pytest.raises(pytest.skip.Exception, match='inbox bridge'):
        verification_code('qa@example.invalid', time.time())
    assert verification_code('qa+clerk_test@example.invalid', time.time()) == '424242'


def test_otp_bridge_rejects_stale_and_other_account_codes(monkeypatch):
    import android_ui
    import boto3
    monkeypatch.setenv('JOUFT_TEST_SECOND_EMAIL', 'qa@example.invalid')
    monkeypatch.setenv('JOUFT_TEST_SECOND_OTP_SECRET', 'controlled-test-otp')
    attempts = iter([
        dict(email='qa@example.invalid', code='111111', issued_at=1),
        dict(email='other@example.invalid', code='222222', issued_at=200),
        dict(email='qa@example.invalid', code='333333', issued_at=200)])
    from types import SimpleNamespace
    monkeypatch.setattr(boto3, 'client', lambda *a, **k: SimpleNamespace(get_secret_value=lambda **k: {'SecretString': json.dumps(next(attempts))}))
    monkeypatch.setattr(android_ui.time, 'sleep', lambda _: None)
    assert android_ui.verification_code('qa@example.invalid', 100) == '333333'


def test_observer_session_renewal_pins_owner_and_caches_token(monkeypatch):
    monkeypatch.setenv('JOUFT_TEST_CLERK_SESSION_A', 'sess_fixture')
    monkeypatch.setenv('JOUFT_TEST_CLERK_SECRET', 'sk_test_fake')
    calls = []
    from types import SimpleNamespace
    class Response:
        def __init__(self, record): self.record = record
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps(self.record).encode()
    def opening(request, timeout):
        calls.append(request.get_method())
        assert request.full_url.startswith('https://api.clerk.com/v1/sessions/sess_fixture')
        return Response({'user_id': 'fixture-A', 'status': 'active'} if request.get_method() == 'GET' else {'jwt': jwt('fixture-A', time.time() + 60)})
    monkeypatch.setattr(support.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=opening))
    api = API('https://staging.jouft.com', subject='fixture-A')
    assert api.token() == api.token()
    assert calls == ['GET', 'POST']


def test_creation_workflow_requires_photos_before_writing_archive(tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'environment': 'staging', 'reviewed_by': 'QA', 'verified_build': '4'}))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/package_devicefarm_android.py'),
        '--scenario', 'android_workflows', '--workflow', 'background_analysis', '--manifest', str(manifest),
        '--output', str(tmp_path / 'out')], capture_output=True)
    assert result.returncode != 0 and not (tmp_path / 'out/android_workflows.zip').exists()


@pytest.mark.parametrize('email,accepted', [('verified@example.invalid', True), ('editable-profile@example.invalid', False)])
def test_observer_login_uses_verified_auth_identity_not_profile_email(monkeypatch, email, accepted):
    from types import SimpleNamespace
    monkeypatch.setenv('JOUFT_TEST_CLERK_SECRET', 'sk_test_fake')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self):
            return json.dumps({'id': 'user_fixture', 'email_addresses': [
                {'email_address': 'verified@example.invalid', 'verification': {'status': 'verified'}},
                {'email_address': 'editable-profile@example.invalid', 'verification': None}]}).encode()
    monkeypatch.setattr(support.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=lambda *a, **k: Response()))
    api = API('https://staging.jouft.com', subject='user_fixture')
    monkeypatch.setattr(api, 'get', lambda path: {'user_id': 'user_fixture', 'email': None})
    if accepted:
        api.assert_identity(email)
    else:
        with pytest.raises(AssertionError, match='accounts differ'):
            api.assert_identity(email)


def test_provider_field_uses_editable_hint_instead_of_tapping_a_label():
    from types import SimpleNamespace
    field = SimpleNamespace(id='native-expiry-field', is_displayed=lambda: True, is_enabled=lambda: True)
    driver = SimpleNamespace(find_elements=lambda by, query: [field] if '@hint="MM / YY"' in query else [])
    app = SimpleNamespace(driver=driver, elements=lambda _: pytest.fail('Hinted provider field should resolve before static labels'))
    assert Controls(app).field('Expiration date') is field


def test_devicefarm_resigning_requires_same_embedded_code_and_config(tmp_path, monkeypatch):
    path, manifest = staged_apk(tmp_path)
    with zipfile.ZipFile(path, 'a') as z:
        z.writestr('assets/index.android.bundle', b'controlled staging code')
    with zipfile.ZipFile(path) as z:
        manifest['config_sha256'] = hashlib.sha256(z.read('assets/app.config')).hexdigest()
        manifest['js_bundle_sha256'] = hashlib.sha256(z.read('assets/index.android.bundle')).hexdigest()
    monkeypatch.setenv('DEVICEFARM_RUN_ARN', 'arn:aws:devicefarm:us-west-2:account:run:test')
    verify_staging_apk(manifest, path)
    manifest['js_bundle_sha256'] = '0' * 64
    with pytest.raises(AssertionError, match='code digest'):
        verify_staging_apk(manifest, path)


def test_login_otp_ignores_disabled_email_field():
    from android_ui import AndroidUI
    from types import SimpleNamespace
    email = SimpleNamespace(is_enabled=lambda: False, is_displayed=lambda: True)
    code = SimpleNamespace(is_enabled=lambda: True, is_displayed=lambda: True)
    hidden = SimpleNamespace(is_enabled=lambda: True, is_displayed=lambda: False)
    ui = object.__new__(AndroidUI)
    ui.driver = SimpleNamespace(find_elements=lambda *args: [email, code, hidden])
    assert ui.editable_fields() == [code]


def test_unicode_ui_selector_preserves_actual_label_characters():
    from android_ui import AndroidUI
    from appium.webdriver.common.appiumby import AppiumBy
    from types import SimpleNamespace
    queries = []
    field = SimpleNamespace(id='native-expiry-field', is_displayed=lambda: True, is_enabled=lambda: True)
    def find(by, query):
        queries.append((by, query))
        return [field] if by == AppiumBy.ANDROID_UIAUTOMATOR and 'NOTIFICATIONS — VIEW ALL ACTIVITY' in query else []
    ui = object.__new__(AndroidUI); ui.driver = SimpleNamespace(find_elements=find)
    assert ui.elements('Notifications — View all activity') == [field]
    assert not any('\\u2014' in query for _, query in queries)


def test_empty_photo_uses_appium_supported_locator_strategy(monkeypatch):
    from types import SimpleNamespace
    from appium.webdriver.common.appiumby import AppiumBy
    spec = importlib.util.spec_from_file_location('android_regression', ROOT / 'tests/devicefarm/tests/test_android_regression.py')
    regression = importlib.util.module_from_spec(spec); spec.loader.exec_module(regression)
    strategies = []
    button = SimpleNamespace(is_enabled=lambda: False)
    def find(by, value):
        strategies.append(by); return [button]
    ui = SimpleNamespace(tab=lambda *a: None, has=lambda label: label == '0/6', driver=SimpleNamespace(find_elements=find))
    regression.test_create_without_photos(ui)
    assert strategies == [AppiumBy.ANDROID_UIAUTOMATOR]


@pytest.mark.parametrize('notice,expected', [
    ("We couldn't determine this item's value. It needs manual review before publishing. You do not need to set a value.", True),
    ('This item needs manual pricing review before publishing. You do not need to set a value.', True),
    ('Review your changes before saving', False)])
def test_pricing_gate_recognizes_client_and_server_contracts(notice, expected):
    spec = importlib.util.spec_from_file_location('android_regression_pricing', ROOT / 'tests/devicefarm/tests/test_android_regression.py')
    regression = importlib.util.module_from_spec(spec); spec.loader.exec_module(regression)
    assert regression.has_manual_pricing_notice({notice}) is expected


def test_credential_wait_requires_both_fields_not_partial_modal(monkeypatch):
    import android_ui
    from selenium.webdriver.support.ui import WebDriverWait as RealWait
    ui = object.__new__(android_ui.AndroidUI); ui.driver = object()
    states = iter([[], ['email'], ['email', 'password']])
    monkeypatch.setattr(ui, 'editable_fields', lambda: next(states))
    monkeypatch.setattr(android_ui, 'WebDriverWait', lambda driver, timeout: RealWait(driver, 1, poll_frequency=0.001))
    assert ui.wait_editable_fields() == ['email', 'password']


@pytest.mark.parametrize('case', ['registration', 'password_recovery'])
def test_missing_auth_fixture_credentials_are_blocked_not_key_errors(monkeypatch, case):
    manifest = json.loads((ROOT / 'tests/devicefarm/android-fixtures.example.json').read_text())
    for key in ['JOUFT_TEST_REGISTRATION_EMAIL', 'JOUFT_TEST_REGISTRATION_PASSWORD',
                'JOUFT_TEST_RECOVERY_EMAIL', 'JOUFT_TEST_RECOVERY_PASSWORD', 'JOUFT_TEST_RECOVERY_NEW_PASSWORD']:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(pytest.skip.Exception, match='missing workflow environment reference'):
        workflows.prerequisites(case, manifest)


@pytest.mark.parametrize('before,after,expected', [
    (['old first', 'old second'], ['new draft', 'old first'], True),
    (['old first', 'old second'], ['old first', 'old second'], False),
    ([], [], False),
    (['same title'], ['same title', 'older card'], True)])
def test_creation_detection_handles_fixed_accessibility_viewport(before, after, expected):
    path = ROOT / 'tests/devicefarm/tests/test_create_listing.py'
    spec = importlib.util.spec_from_file_location('create_listing_viewport', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.new_listing_card_visible(before, after) is expected

@pytest.mark.parametrize('package,legacy,expected', [
    ('com.google.android.photopicker', [], ['compose-photo']),
    ('com.google.android.providers.media.module', ['legacy-photo'], ['legacy-photo']),
    ('com.jouft.app.dev', [], []),
])
def test_photo_picker_supports_compose_without_selecting_app_images(package, legacy, expected):
    from android_ui import android_photo_thumbnails
    class Driver:
        current_package = package
        def find_elements(self, strategy, query):
            return legacy if 'icon_thumbnail' in query else ['compose-photo']
    assert android_photo_thumbnails(Driver()) == expected


def test_tab_already_at_destination_does_not_require_hidden_footer():
    from android_ui import AndroidUI
    app = object.__new__(AndroidUI)
    app.has = lambda label: label == 'Add Photos'
    app.tab('Create', 'Add Photos')

@pytest.mark.parametrize('selection,second,expected', [
    ('registration', False, 0), ('camera_capture', False, 2), ('registration', True, 2),
])
def test_registration_login_secret_is_region_scoped_and_isolated(monkeypatch, selection, second, expected):
    import run_remote
    from types import SimpleNamespace
    env = {'JOUFT_TEST_SCENARIO': 'android_workflows', 'JOUFT_TEST_WORKFLOW_CASES': selection,
           'JOUFT_TEST_REGISTRATION_SECRET': 'test/registration', 'DEVICEFARM_LOG_DIR': '/tmp/unit-not-written'}
    if second:
        env['JOUFT_TEST_SECOND_SECRET'] = 'test/shared-b'
    monkeypatch.setattr(run_remote.os, 'environ', env)
    reads = []
    def client(service, region_name):
        class Secrets:
            def get_secret_value(self, SecretId):
                reads.append((region_name, SecretId))
                return {'SecretString': json.dumps({'email': 'fixture+clerk_test@example.com', 'password': 'fake-unit-fixture-only'})}
        return Secrets()
    monkeypatch.setattr(run_remote.boto3, 'client', client)
    calls = []
    def run(args, env):
        calls.append(env)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(run_remote.subprocess, 'run', run)
    assert run_remote.main() == expected
    if expected == 0:
        assert ('us-east-1', 'test/registration') in reads
        assert calls[0]['JOUFT_TEST_REGISTRATION_EMAIL'] == 'fixture+clerk_test@example.com'
        assert 'JOUFT_TEST_SECOND_EMAIL' not in calls[0]
    else:
        assert not calls
        assert ('us-east-1', 'test/registration') not in reads


def test_broad_android_runs_load_provisioned_second_account_from_virginia(monkeypatch):
    import run_remote
    from types import SimpleNamespace
    env = {'JOUFT_TEST_SCENARIO': 'android_regression', 'DEVICEFARM_LOG_DIR': '/tmp/unit-not-written'}
    monkeypatch.setattr(run_remote.os, 'environ', env)
    reads, calls = [], []
    def client(service, region_name):
        class Secrets:
            def get_secret_value(self, SecretId):
                reads.append((region_name, SecretId))
                email = 'second+clerk_test@example.com' if SecretId.endswith('-b') else 'first+clerk_test@example.com'
                return {'SecretString': json.dumps({'email': email, 'password': 'fake-unit-fixture-only'})}
        return Secrets()
    monkeypatch.setattr(run_remote.boto3, 'client', client)
    def run(args, env):
        calls.append(env)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(run_remote.subprocess, 'run', run)
    assert run_remote.main() == 0
    assert ('us-east-1', 'jouft/devicefarm/staging-login-b') in reads
    assert calls[0]['JOUFT_TEST_SECOND_EMAIL'] == 'second+clerk_test@example.com'


def test_nested_marketplace_accessibility_buttons_are_one_listing():
    from android_ui import unique_listing_card
    from types import SimpleNamespace
    outer = SimpleNamespace(rect={'x': 10, 'y': 20, 'width': 300, 'height': 500})
    image = SimpleNamespace(rect={'x': 10, 'y': 20, 'width': 300, 'height': 350})
    assert unique_listing_card([outer, image]) is image


def test_separate_same_title_cards_remain_ambiguous():
    from android_ui import unique_listing_card
    from types import SimpleNamespace
    cards = [SimpleNamespace(rect={'x': 10, 'y': y, 'width': 300, 'height': 400}) for y in [20, 450]]
    with pytest.raises(AssertionError, match='one visible card'):
        unique_listing_card(cards)


def test_duplicate_node_queries_do_not_duplicate_a_card():
    from android_ui import unique_listing_card
    from types import SimpleNamespace
    card = SimpleNamespace(rect={'x': 10, 'y': 20, 'width': 300, 'height': 400})
    assert unique_listing_card([card, card]) is card
