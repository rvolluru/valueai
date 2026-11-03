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


def test_shared_ai_secrets_are_preserved_without_copying_runtime_secrets():
    original = definition()
    original['containerDefinitions'][0]['secrets'] = [
        dict(name=name, valueFrom=f'{module.AI_SECRET_ARN}:{name}::')
        for name in sorted(module.AI_SECRET_KEYS)
    ]
    candidate = module.prepare(original, 'new')
    assert candidate['containerDefinitions'][0]['secrets'] == original['containerDefinitions'][0]['secrets']


@pytest.mark.parametrize('name,reference', [
    ('DATABASE_URL', f'{module.AI_SECRET_ARN}:DATABASE_URL::'),
    ('STRIPE_SECRET_KEY', f'{module.AI_SECRET_ARN}:STRIPE_SECRET_KEY::'),
    ('OPENAI_API_KEY', 'arn:aws:secretsmanager:us-east-1:537595754494:secret:other:OPENAI_API_KEY::'),
])
def test_rejects_unapproved_secret_references(name, reference):
    original = definition()
    original['containerDefinitions'][0]['secrets'] = [dict(name=name, valueFrom=reference)]
    with pytest.raises(RuntimeError):
        module.prepare(original, 'new')


def test_rejects_duplicate_plaintext_and_secret_ai_key():
    original = definition(OPENAI_API_KEY='fixture-only')
    original['containerDefinitions'][0]['secrets'] = [
        dict(name='OPENAI_API_KEY', valueFrom=f'{module.AI_SECRET_ARN}:OPENAI_API_KEY::')]
    with pytest.raises(RuntimeError):
        module.prepare(original, 'new')


def test_production_model_settings_replace_stale_values_without_other_changes():
    original = definition(GPT_ITEM_PROFILE_GEMINI_MODEL='old', GPT_ITEM_PROFILE_MODEL='stale',
                          GPT_ITEM_PROFILE_TIMEOUT_S='25')
    models = {'GPT_ITEM_PROFILE_GEMINI_MODEL': 'gemini-3.8-flash',
              'GPT_NEW_LISTING_PRICING_MODEL': 'gpt-6.1-sol',
              'GPT_PRICING_MODEL_ROUTING_ENABLED': 'true'}
    result = module.prepare(original, 'new', models)
    env = {e['name']: e['value'] for e in result['containerDefinitions'][0]['environment']}
    assert {k: v for k, v in env.items() if k in module.MODEL_SETTINGS_KEYS} == models
    assert 'GPT_ITEM_PROFILE_TIMEOUT_S' not in env
    assert original['containerDefinitions'][0]['image'] == 'old'


def test_model_sync_cannot_copy_production_credentials():
    with pytest.raises(RuntimeError):
        module.prepare(definition(), 'new', {'DATABASE_URL': 'production-database'})


def test_analysis_parity_includes_limits_and_preserves_staging_data():
    original = definition(GPT_ITEM_PROFILE_TIMEOUT_S='25', GPT_ITEM_PROFILE_MAX_IMAGES='2',
                          STRIPE_SECRET_KEY='sk_test_fixture')
    settings = {'GPT_ITEM_PROFILE_TIMEOUT_S': '240', 'GPT_ITEM_PROFILE_MAX_IMAGES': '6',
                'GPT_ITEM_PROFILE_PROVIDER_ORDER': 'hybrid,gemini,openai',
                'LISTING_ANALYSIS_ATTEMPT_TIMEOUT_S': '300',
                'IMAGE_STAGING_PHOTOROOM_ENABLED': 'true'}
    candidate = module.prepare(original, 'new', settings)
    env = {e['name']:e['value'] for e in candidate['containerDefinitions'][0]['environment']}
    assert {k:v for k,v in env.items() if k in module.ANALYSIS_SETTINGS_KEYS} == settings
    assert env['STRIPE_SECRET_KEY'] == 'sk_test_fixture'
    assert env['DATABASE_URL'].startswith('postgresql://user:pass@valueai-staging-postgres.')


@pytest.mark.parametrize('key', ['OPENAI_API_KEY', 'S3_BUCKET', 'SQS_ANALYSIS_QUEUE_URL',
                               'GPT_ITEM_PROFILE_VERTEX_SEARCH_PROJECT_ID',
                               'GPT_ITEM_PROFILE_VERTEX_SEARCH_DATASTORE'])
def test_analysis_sync_does_not_copy_credentials_or_production_data_sources(key):
    with pytest.raises(RuntimeError):
        module.prepare(definition(), 'new', {key:'production-value'})
