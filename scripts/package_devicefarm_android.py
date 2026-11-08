"""Build a reviewable Android test ZIP/spec; optionally validate uploads, never schedule runs."""
import argparse
import json
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'arn:aws:devicefarm:us-west-2:537595754494:project:dfc7f940-6cb8-4ea1-b01f-e887db6da2f7'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['android_smoke', 'android_regression', 'android_workflows', 'android_full'], default='android_smoke')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--fixture-dir', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/android-suite')
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--profile', default='rajesh_volluru')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'tests/devicefarm'
    manifest = None
    if args.manifest:
        manifest = json.loads(args.manifest.read_text())
        assert manifest.get('environment') == 'staging' and manifest.get('reviewed_by') and manifest.get('verified_build'), 'Manifest must identify staging build and reviewer'
        def inspect(value):
            if isinstance(value, dict):
                if value.get('action') == 'input' and any(word in value.get('label', '').lower()
                    for word in ['password', 'token', 'verification', 'card number', 'cvc', 'security code']):
                    assert value.get('env') and 'value' not in value, 'Sensitive input must use an environment reference'
                for key, entry in value.items():
                    assert key.lower() not in {'password', 'token', 'api_key', 'secret', 'authorization'}, 'Do not package credentials'
                    inspect(entry)
            elif isinstance(value, list):
                for entry in value: inspect(entry)
            elif isinstance(value, str):
                assert 'X-Amz-Signature=' not in value and 'X-Goog-Signature=' not in value, 'Do not package signed URLs'
        inspect(manifest)
    archive = args.output / (args.scenario + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ['requirements.txt', 'run_remote.py', 'android_ui.py']:
            z.write(source / name, name)
        for path in sorted((source / 'tests').glob('*.py')):
            z.write(path, 'tests/' + path.name)
        if manifest:
            z.writestr('android-fixtures.json', json.dumps(manifest, indent=2))
        if args.fixture_dir:
            photos = sorted(args.fixture_dir.glob('*.jpg'))
            assert 1 <= len(photos) <= 6
            for photo in photos: z.write(photo, 'fixtures/' + photo.name)
    if args.scenario == 'android_full':
        assert args.fixture_dir, 'Full suite includes creation: provide complete one-item JPG fixture set'
    spec = args.output / (args.scenario + '-spec.yml')
    spec.write_text((source / 'android-regression-test-spec.yml').read_text().replace(
        'JOUFT_TEST_SCENARIO=android_smoke', 'JOUFT_TEST_SCENARIO=' + args.scenario))
    metadata = {'scenario': args.scenario, 'package': str(archive), 'spec': str(spec),
                'device_run_verified': False, 'contains_manifest': manifest is not None}
    if args.upload:
        import boto3
        client = boto3.Session(profile_name=args.profile, region_name='us-west-2').client('devicefarm')
        for path, kind in [(archive, 'APPIUM_PYTHON_TEST_PACKAGE'), (spec, 'APPIUM_PYTHON_TEST_SPEC')]:
            upload = client.create_upload(projectArn=PROJECT, name=path.name, type=kind)['upload']
            with urllib.request.urlopen(urllib.request.Request(upload['url'], data=path.read_bytes(), method='PUT',
                headers={'Content-Type': 'application/octet-stream'})) as response:
                assert response.status == 200
            for _ in range(60):
                upload = client.get_upload(arn=upload['arn'])['upload']
                if upload['status'] in {'SUCCEEDED', 'FAILED'}: break
                time.sleep(2)
            assert upload['status'] == 'SUCCEEDED', 'AWS test upload validation failed'
            metadata[kind] = upload['arn']
    (args.output / 'metadata.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
