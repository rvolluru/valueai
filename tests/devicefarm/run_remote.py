"""Read credentials in memory and run pytest without embedding secrets in YAML."""
import os
from pathlib import Path
import subprocess
import sys

import boto3


def main():
    import json
    try:
        response = boto3.client('secretsmanager', region_name='us-west-2').get_secret_value(
            SecretId='jouft/devicefarm/staging-login')
        credentials = json.loads(response['SecretString'])
        if not credentials.get('password') or not credentials.get('email'):
            raise ValueError('Missing credentials')
    except Exception:
        print('Staging test credentials are unavailable. Populate the Device Farm secret first.')
        return 2
    environment = os.environ.copy()
    environment.update({
        'JOUFT_TEST_EMAIL': credentials['email'],
        'JOUFT_TEST_PASSWORD': credentials['password'],
        'JOUFT_TEST_TARGET': 'staging', 'JOUFT_TEST_CATEGORY': environment.get('JOUFT_TEST_CATEGORY', 'Clothes'),
        'JOUFT_TEST_SIZE': environment.get('JOUFT_TEST_SIZE', 'S'),
        'JOUFT_TEST_PHOTOS': str(Path('fixtures').resolve()),
        'APPIUM_SERVER_URL': 'http://127.0.0.1:4723/wd/hub',
    })
    if credentials.get('api_token'):
        environment['JOUFT_TEST_API_TOKEN_A'] = credentials['api_token']
    if credentials.get('clerk_session_id'):
        environment['JOUFT_TEST_CLERK_SESSION_A'] = credentials['clerk_session_id']
    scenario = environment.get('JOUFT_TEST_SCENARIO', 'create')
    tests = {'create': 'tests/test_create_listing.py',
             'review_publish': 'tests/test_review_publish.py',
             'review_publish_existing': 'tests/test_review_publish_existing.py',
             'android_smoke': 'tests/test_android_regression.py',
             'android_regression': 'tests/test_android_regression.py',
             'android_workflows': 'tests/test_android_workflows.py',
             'android_full': 'tests/'}
    if scenario not in tests:
        print('Unknown Device Farm test scenario')
        return 2
    if scenario.startswith('android_'):
        environment['JOUFT_TEST_PLATFORM'] = 'Android'
        environment['JOUFT_TEST_REQUIRE_COMPLETE'] = '1'
        selected_workflows = set(environment.get('JOUFT_TEST_WORKFLOW_CASES', '').split(','))
        uses_second_account = scenario in {'android_regression', 'android_full'} or (
            scenario == 'android_workflows' and (not environment.get('JOUFT_TEST_WORKFLOW_CASES') or
            bool(selected_workflows & {'trade_send', 'trade_decline', 'trade_accept',
                                      'trade_stale_action', 'delete_disposable', 'push_delivery'})))
        second_secret = environment.get('JOUFT_TEST_SECOND_SECRET') or (
            'jouft/devicefarm/staging-login-b' if uses_second_account else None)
        if second_secret:
            try:
                second = json.loads(boto3.client('secretsmanager', region_name=environment.get(
                    'JOUFT_TEST_SECOND_SECRET_REGION', 'us-east-1')).get_secret_value(
                    SecretId=second_secret)['SecretString'])
                environment['JOUFT_TEST_SECOND_EMAIL'] = second['email']
                environment['JOUFT_TEST_SECOND_PASSWORD'] = second['password']
                if second.get('clerk_session_id'):
                    environment['JOUFT_TEST_CLERK_SESSION_B'] = second['clerk_session_id']
                if second.get('api_token'):
                    environment['JOUFT_TEST_API_TOKEN_B'] = second['api_token']
            except Exception:
                print('Second staging account secret is unavailable.')
                return 2
    registration_secret = environment.get('JOUFT_TEST_REGISTRATION_SECRET')
    if registration_secret:
        # Bootstrap a NEW disposable account through the normal registration
        # case, without identifying it as an already-shared A/B login.
        if scenario != 'android_workflows' or environment.get('JOUFT_TEST_WORKFLOW_CASES') != 'registration' or environment.get('JOUFT_TEST_SECOND_SECRET'):
            print('Registration login secret requires an isolated registration-only run.')
            return 2
        try:
            registration = json.loads(boto3.client('secretsmanager', region_name=environment.get(
                'JOUFT_TEST_REGISTRATION_SECRET_REGION', 'us-east-1')).get_secret_value(
                SecretId=registration_secret)['SecretString'])
            assert registration['email'] and registration['password']
            environment['JOUFT_TEST_REGISTRATION_EMAIL'] = registration['email']
            environment['JOUFT_TEST_REGISTRATION_PASSWORD'] = registration['password']
        except Exception:
            print('Registration credentials secret is unavailable or invalid.')
            return 2
    workflow_secret = environment.get('JOUFT_TEST_WORKFLOW_SECRET')
    if scenario in {'android_workflows', 'android_full'} and workflow_secret:
        try:
            extra = json.loads(boto3.client('secretsmanager', region_name='us-west-2').get_secret_value(
                SecretId=workflow_secret)['SecretString'])
            allowed = {'JOUFT_TEST_CLERK_SECRET', 'JOUFT_TEST_CLERK_SESSION_A', 'JOUFT_TEST_CLERK_SESSION_B',
                'JOUFT_TEST_REGISTRATION_EMAIL', 'JOUFT_TEST_REGISTRATION_PASSWORD', 'JOUFT_TEST_REGISTRATION_DENIED_EMAIL',
                'JOUFT_TEST_RECOVERY_EMAIL', 'JOUFT_TEST_RECOVERY_PASSWORD', 'JOUFT_TEST_RECOVERY_NEW_PASSWORD',
                'JOUFT_TEST_OTP_SECRET', 'JOUFT_TEST_SECOND_OTP_SECRET'}
            assert set(extra) <= allowed and all(isinstance(v, str) for v in extra.values())
            environment.update(extra)
        except Exception:
            print('Workflow credentials secret is unavailable or invalid.')
            return 2
    selection = [tests[scenario]]
    if scenario == 'android_smoke':
        selection += ['-k', 'navigation or empty_search or profile_sections or notification_history or resume_session or signout or create_without_photos or assistant_open_close or trade_inbox_filters or invalid_signin or required_signin_fields']
    if scenario == 'android_full':
        # Each mutating listing flow runs once; do not also invoke standalone
        # existing-publication tests against an arbitrary draft.
        selection = ['tests/test_android_regression.py', 'tests/test_android_workflows.py',
                     'tests/test_review_publish.py']
    case_filter = environment.get('JOUFT_TEST_CASE_FILTER')
    if case_filter:
        assert scenario in {'android_regression', 'android_workflows', 'android_full'}, 'Case filtering is for explicit focused retests'
        selection += ['-k', case_filter]
    # Tracebacks can contain WebDriver request payloads, including send_keys.
    return subprocess.run([
        sys.executable, '-m', 'pytest', *selection, '-v', '--tb=no',
        '--junitxml', str(Path(os.environ['DEVICEFARM_LOG_DIR']) / 'junitreport.xml'),
    ], env=environment).returncode


if __name__ == '__main__':
    raise SystemExit(main())
