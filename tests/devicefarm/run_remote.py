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
        'JOUFT_TEST_TARGET': 'staging', 'JOUFT_TEST_CATEGORY': 'Clothes',
        'JOUFT_TEST_SIZE': 'S',
        'JOUFT_TEST_PHOTOS': str(Path('fixtures').resolve()),
        'APPIUM_SERVER_URL': 'http://127.0.0.1:4723/wd/hub',
    })
    # Tracebacks can contain WebDriver request payloads, including send_keys.
    return subprocess.run([
        sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=no',
        '--junitxml', str(Path(os.environ['DEVICEFARM_LOG_DIR']) / 'junitreport.xml'),
    ], env=environment).returncode


if __name__ == '__main__':
    raise SystemExit(main())
