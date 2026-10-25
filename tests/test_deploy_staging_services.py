import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('staging_deploy', Path(__file__).parents[1] / 'scripts/deploy_staging_services.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def definition(**overrides):
    env = dict(APP_ENV='staging', DATABASE_URL='postgresql://user:pass@valueai-staging-postgres.example/db',
        S3_BUCKET='valueai-staging-uploads-example', SQS_ANALYSIS_QUEUE_URL='https://sqs.example/valueai-staging-analysis')
    env.update(overrides)
    return dict(family='valueai-staging-api', revision=9,
        containerDefinitions=[dict(name='api', image='old', environment=[dict(name=k, value=v) for k, v in env.items()])])


def test_staging_deploy_preserves_original_and_enables_guarded_features():
    original = definition()
    candidate = module.prepare(original, 'new')
    env = {v['name']: v['value'] for v in candidate['containerDefinitions'][0]['environment']}
    assert env['LISTING_AGENT_ENABLED'] == env['ASSISTANT_CONVERSATIONS_ENABLED'] == 'true'
    assert candidate['containerDefinitions'][0]['image'] == 'new'
    assert original['containerDefinitions'][0]['image'] == 'old'
    assert 'revision' not in candidate


@pytest.mark.parametrize('values', [dict(APP_ENV='prod'), dict(DATABASE_URL='postgresql://prod.example/db'),
    dict(S3_BUCKET='valueai-mvp-uploads'), dict(SQS_ANALYSIS_QUEUE_URL='https://sqs.example/production'),
    dict(STRIPE_SECRET_KEY='sk_live_fixture'), dict(SHIPPO_API_KEY='shippo_live_fixture')])
def test_staging_deploy_rejects_production_resources_and_live_billing(values):
    with pytest.raises(RuntimeError):
        module.prepare(definition(**values), 'new')
