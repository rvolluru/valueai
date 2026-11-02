#!/usr/bin/env python3
"""Save the terminal's staging test password without putting it in CLI arguments."""
import json
import os
import subprocess

password = os.environ.get('JOUFT_TEST_PASSWORD')
if not password:
    raise SystemExit('JOUFT_TEST_PASSWORD is missing or not exported in this terminal.')
result = subprocess.run([
    'aws', 'secretsmanager', 'put-secret-value',
    '--secret-id', 'jouft/devicefarm/staging-login', '--secret-string', 'file:///dev/stdin',
    '--region', 'us-west-2', '--profile', 'rajesh_volluru', '--no-cli-pager',
], input=json.dumps({'email': 'leavethemessage@gmail.com', 'password': password}),
    text=True, capture_output=True)
if result.returncode:
    raise SystemExit('Could not save the password. Check AWS login and Secrets Manager permissions.')
print('Staging test credentials saved to Secrets Manager. Password was not displayed.')
