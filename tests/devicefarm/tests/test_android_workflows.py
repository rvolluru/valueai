"""Fixture-driven UI workflows for controlled mutation and host-dependent cases.

Missing recipes are Blocked, not placeholder passes. These recipes are test code:
review and version them with a run's fixture manifest before execution.
"""
import json
import os
from pathlib import Path

import pytest
from android_ui import AndroidUI

# Known business scenarios; do not silently accept typo/unknown recipe names.
WORKFLOWS = {
    'registration': ('QA-008', False),
    'password_recovery': ('QA-005', False),
    'profile_save_restore': ('QA-050', False),
    'style_matching': ('QA-040', False),
    'edit_save_restore': ('QA-036', False),
    'delete_disposable': ('QA-038', False),
    'like_restore': ('QA-041', False),
    'trade_send': ('QA-042', True),
    'trade_decline': ('QA-043', False),
    'trade_accept': ('QA-044', True),
    'trade_stale_action': ('QA-045', True),
    'shipping_address_save_restore': ('QA-046', False),
    'shipping_quote_label': ('QA-047', True),
    'payment_add_default_remove': ('QA-048', True),
    'subscription_change_cancel': ('QA-049', True),
    'push_delivery': ('QA-053', False),
    'photo_permission_recovery': ('QA-017', False),
    'camera_capture': ('QA-016', False),
    'offline_recovery': ('QA-059', False),
    'background_analysis': ('QA-060', False),
    'assistant_listing': ('QA-058', False),
}


def execute(app, step):
    action = step['action']
    if action == 'tab':
        app.tab(step['label'], step['expect'])
    elif action == 'tap':
        app.tap(step['label'], scroll=step.get('scroll', False))
    elif action == 'input':
        # Password/token values must be referenced through the environment.
        value = os.environ[step['env']] if 'env' in step else step['value']
        app.input(step['label'], value)
    elif action == 'wait':
        app.wait(step['label'], timeout=min(int(step.get('timeout', 30)), 900))
    elif action == 'absent':
        assert not app.has(step['label']), 'Unexpected control/text present'
    elif action == 'search':
        app.search(step['area'], step['value'])
    elif action == 'open_listing':
        app.open_listing(step['area'], step['title'])
    elif action == 'switch_account':
        account = step['account']
        assert account in {'A', 'B'}
        suffix = 'SECOND_' if account == 'B' else ''
        app.logout()
        app.login(os.environ['JOUFT_TEST_' + suffix + 'EMAIL'], os.environ['JOUFT_TEST_' + suffix + 'PASSWORD'])
    elif action == 'sign_out':
        app.logout()
    elif action == 'back':
        app.driver.back()
    elif action == 'relaunch':
        app.driver.terminate_app(app.package); app.driver.activate_app(app.package)
    else:
        raise AssertionError('Unsupported workflow action: ' + action)


def validate(recipe, financial=False):
    assert recipe.get('reviewed_by'), 'Recipe requires a reviewer'
    assert recipe.get('fixture_ids'), 'Record controlled entity IDs / account aliases'
    if financial:
        assert recipe.get('sandbox_verified_by') and recipe.get('sandbox_environment') == 'staging-test-mode', 'Sandbox verification is required'
    for stage in ['steps', 'verify', 'cleanup']:
        assert isinstance(recipe.get(stage), list) and recipe[stage], 'Recipe needs steps, verification and cleanup'
    assert any(s.get('action') == 'wait' for s in recipe['verify']), 'Verification must assert an observable final state'
    for step in recipe['steps'] + recipe['verify'] + recipe['cleanup']:
        assert step.get('action') in {'tab', 'tap', 'input', 'wait', 'absent', 'search', 'open_listing', 'back', 'relaunch', 'switch_account', 'sign_out'}


@pytest.mark.parametrize('workflow', WORKFLOWS)
def test_controlled_workflow(workflow, request):
    path = Path(os.environ.get('JOUFT_TEST_FIXTURES', 'android-fixtures.json'))
    manifest = json.loads(path.read_text()) if path.exists() else {}
    recipe = manifest.get('workflows', {}).get(workflow)
    if not recipe:
        pytest.skip('Blocked: no reviewed fixture recipe for ' + workflow)
    financial = WORKFLOWS[workflow][1]
    if financial and os.environ.get('JOUFT_TEST_SANDBOX_CONFIRMED') != '1':
        pytest.skip('Blocked: sandbox payment/shipping configuration not confirmed')
    validate(recipe, financial)
    if any(step.get('action') == 'switch_account' and step.get('account') == 'B'
           for stage in ['steps', 'verify', 'cleanup'] for step in recipe[stage]):
        if not os.environ.get('JOUFT_TEST_SECOND_EMAIL') or not os.environ.get('JOUFT_TEST_SECOND_PASSWORD'):
            pytest.skip('Blocked: workflow requires second staging account')
    app = AndroidUI()
    original_error = None
    authenticated = False
    try:
        app.login(os.environ['JOUFT_TEST_EMAIL'], os.environ['JOUFT_TEST_PASSWORD'])
        authenticated = True
        for step in recipe['steps'] + recipe['verify']:
            execute(app, step)
    except Exception as exc:
        original_error = exc
        raise
    finally:
        folder = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm')) / 'cases'
        folder.mkdir(parents=True, exist_ok=True)
        try:
            app.capture(folder / (workflow + '.png'))
        except Exception:
            pass
        try:
            # Cleanup is reviewed alongside actions and must restore disposable data.
            for step in (recipe['cleanup'] if authenticated else []):
                execute(app, step)
        except Exception:
            if original_error is None:
                raise AssertionError('Workflow cleanup failed; inspect controlled fixture state')
        finally:
            app.driver.quit()
