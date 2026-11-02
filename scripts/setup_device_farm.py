#!/usr/bin/env python3
"""Create/reuse Jouft Device Farm projects; never starts billable sessions/runs."""

import argparse
import json
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='rajesh_volluru')
    args = parser.parse_args()

    def aws(*command):
        result = subprocess.run(
            ['aws', 'devicefarm', *command, '--region', 'us-west-2',
             '--profile', args.profile, '--output', 'json', '--no-cli-pager'],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)

    def named(items, name):
        return next((item for item in items if item['name'] == name), None)

    project = named(aws('list-projects')['projects'], 'jouft-mobile')
    if project is None:
        project = aws('create-project', '--name', 'jouft-mobile',
                      '--default-job-timeout-minutes', '15')['project']
    pools = aws('list-device-pools', '--arn', project['arn'])['devicePools']
    selected = {}
    for platform in ('ANDROID', 'IOS'):
        name = 'jouft-' + platform.lower()
        pool = named(pools, name)
        if pool is None:
            pool = aws(
                'create-device-pool', '--project-arn', project['arn'],
                '--name', name, '--max-devices', '1', '--rules',
                json.dumps([{'attribute': 'PLATFORM', 'operator': 'EQUALS',
                             'value': json.dumps(platform)}]),
            )['devicePool']
        selected[platform] = pool['arn']
    desktop = named(aws('list-test-grid-projects')['testGridProjects'],
                    'jouft-desktop')
    if desktop is None:
        desktop = aws('create-test-grid-project', '--name', 'jouft-desktop',
                      '--description', 'Jouft staging desktop browser testing with Selenium')['testGridProject']
    print(json.dumps({'region': 'us-west-2', 'mobile_project': project['arn'],
                      'device_pools': selected, 'desktop_project': desktop['arn']}, indent=2))


if __name__ == '__main__':
    main()
