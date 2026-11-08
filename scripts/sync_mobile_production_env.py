"""Mirror public production mobile configuration from AWS to EAS; never print key values."""
import argparse
import json
import subprocess
from pathlib import Path

FIELDS = ('JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY',
          'JOUFT_PRODUCTION_CLERK_ALLOW_TEST_INSTANCE', 'JOUFT_PRODUCTION_CLERK_ISSUER')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='rajesh_volluru')
    parser.add_argument('--secret-id', default='valueai/prod/runtime')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    response = subprocess.run(['aws', 'secretsmanager', 'get-secret-value',
        '--secret-id', args.secret_id, '--region', args.region, '--profile', args.profile,
        '--output', 'json'], capture_output=True, text=True)
    if response.returncode:
        raise SystemExit('Could not read production mobile configuration from AWS.')
    secret = json.loads(json.loads(response.stdout)['SecretString'])
    key = secret.get(FIELDS[0], '')
    if not key.startswith(('pk_live_', 'pk_test_')):
        raise SystemExit('AWS secret has no valid production Clerk publishable configuration.')
    import base64
    if key.startswith('pk_test_'):
        encoded = key[len('pk_test_'):]
        host = base64.b64decode(encoded + '=' * (-len(encoded) % 4)).decode().rstrip('$')
        if secret.get(FIELDS[1]) != 'true' or secret.get(FIELDS[2]) != 'https://' + host:
            raise SystemExit('Production test-instance compatibility must pin the matching issuer.')
    # Explicit false/empty values clear obsolete compatibility configuration when
    # an operator later migrates production to a live Clerk instance.
    values = {FIELDS[0]: key, FIELDS[1]: str(secret.get(FIELDS[1], 'false')),
              FIELDS[2]: str(secret.get(FIELDS[2], ''))}
    cwd = Path(__file__).resolve().parents[1] / 'apps/mobile'
    for name, value in values.items():
        if not args.dry_run:
            result = subprocess.run(['npx', 'eas-cli', 'env:create', 'production',
                '--name', name, '--value', value, '--visibility', 'sensitive',
                '--force', '--non-interactive'], cwd=cwd, capture_output=True, text=True)
            if result.returncode:
                raise SystemExit('EAS synchronization failed for ' + name)
        print(('Validated: ' if args.dry_run else 'Synced: ') + name)


if __name__ == '__main__':
    main()
