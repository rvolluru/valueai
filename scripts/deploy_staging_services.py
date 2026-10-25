"""Roll out an already-built staging image; never targets production resources."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

CLUSTER = 'valueai-staging-cluster'
SERVICES = ('valueai-staging-api', 'valueai-staging-analysis-worker')
ALLOWED = {'family', 'taskRoleArn', 'executionRoleArn', 'networkMode', 'containerDefinitions',
           'volumes', 'placementConstraints', 'requiresCompatibilities', 'cpu', 'memory',
           'pidMode', 'ipcMode', 'proxyConfiguration', 'inferenceAccelerators',
           'ephemeralStorage', 'runtimePlatform', 'enableFaultInjection'}


def aws(*args, payload=None):
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json') as file:
        command = ['aws', 'ecs', *args, '--output', 'json']
        if payload is not None:
            json.dump(payload, file)
            file.flush()
            command += ['--cli-input-json', 'file://' + file.name]
        result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'ECS {args[0]} failed; task definition values are intentionally not printed')
    return json.loads(result.stdout) if result.stdout.strip() else {}


def prepare(definition, image):
    if not definition['family'].startswith('valueai-staging-'):
        raise RuntimeError('Not a staging task family')
    result = {key: value for key, value in definition.items() if key in ALLOWED}
    result = json.loads(json.dumps(result))
    for container in result['containerDefinitions']:
        env = {entry['name']: entry['value'] for entry in container.get('environment', [])}
        if (env.get('APP_ENV') != 'staging'
                or not (urlparse(env.get('DATABASE_URL', '')).hostname or '').startswith('valueai-staging-postgres.')
                or not env.get('S3_BUCKET', '').startswith('valueai-staging-uploads-')
                or 'valueai-staging-analysis' not in env.get('SQS_ANALYSIS_QUEUE_URL', '')):
            raise RuntimeError('Staging data-isolation checks failed')
        if any(str(env.get(key, '')).startswith(('sk_live_', 'pk_live_', 'shippo_live_'))
               for key in ('STRIPE_SECRET_KEY', 'STRIPE_PUBLISHABLE_KEY', 'SHIPPO_API_KEY')):
            raise RuntimeError('Live payment/shipping credentials are not allowed in staging')
        if container.get('secrets'):
            raise RuntimeError('Review secret references for isolation before deployment')
        env.update(LISTING_AGENT_ENABLED='true', ASSISTANT_CONVERSATIONS_ENABLED='true')
        container['environment'] = [{'name': key, 'value': value} for key, value in env.items()]
        container['image'] = image
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    if not args.image.startswith('537595754494.dkr.ecr.us-east-1.amazonaws.com/valueai-staging-api:'):
        raise RuntimeError('Expected a versioned image in the staging ECR repository')
    previous, candidates = {}, {}
    for service in SERVICES:
        details = aws('describe-services', '--cluster', CLUSTER, '--services', service)['services'][0]
        previous[service] = details['taskDefinition']
        definition = aws('describe-task-definition', '--task-definition', details['taskDefinition'])['taskDefinition']
        candidates[service] = prepare(definition, args.image)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'run_ecs_migrations.py'),
        '--cluster', CLUSTER, '--service', SERVICES[0], '--image', args.image], check=True)
    changed = []
    try:
        for service in SERVICES:
            task = aws('register-task-definition', payload=candidates[service])['taskDefinition']['taskDefinitionArn']
            changed.append(service)
            aws('update-service', '--cluster', CLUSTER, '--service', service, '--task-definition', task)
            print(f'Updated {service}: {task}', flush=True)
        aws('wait', 'services-stable', '--cluster', CLUSTER, '--services', *SERVICES)
        from urllib.request import urlopen
        from urllib.error import HTTPError
        with urlopen('https://staging.jouft.com/v1/health', timeout=20) as response:
            if json.load(response).get('status') != 'ok':
                raise RuntimeError('Staging health check failed')
        try:
            urlopen('https://staging.jouft.com/v1/assistant-conversations', timeout=20)
        except HTTPError as exc:
            if exc.code != 401:
                raise RuntimeError('Staging assistant must require sign-in, not return 404/500') from exc
        else:
            raise RuntimeError('Unauthenticated assistant access must be rejected')
    except BaseException:
        for service in changed:
            aws('update-service', '--cluster', CLUSTER, '--service', service, '--task-definition', previous[service])
        if changed:
            aws('wait', 'services-stable', '--cluster', CLUSTER, '--services', *changed)
        raise
    print('Staging API and worker stable. Production was not targeted.', flush=True)


if __name__ == '__main__':
    main()
