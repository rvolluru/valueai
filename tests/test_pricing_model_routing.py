import copy
import threading

import pytest

from app.db import Database
from app.gpt_item_profile import GptItemProfiler, GptItemProfileResult
from app.pricing_models import resolve_pricing_model


def insert(db, listing_id, owner='owner'):
    db.insert_listing(listing_id=listing_id, owner_subject=owner, owner_name='Owner', title='Jacket',
        mode='trade', category='clothes', brand='Louis Vuitton', condition='New', size='M',
        estimated_value=100, city='', image=None, images=[], description='', wants='', tags=[],
        source_item_id=None, analysis=None, status='Review')


@pytest.fixture
def database(tmp_path, monkeypatch):
    from app import migrations
    url = f"sqlite:///{tmp_path / 'cohorts.db'}"
    db = Database(url)
    full = migrations.MIGRATIONS
    with monkeypatch.context() as scoped:
        scoped.setattr(migrations, 'MIGRATIONS', full[:-1])
        db.initialize()
        insert(db, 'legacy')
    assert migrations.migrate(db) == ['0008_listing_pricing_models']
    for key in ('new', 'duplicate', 'other'):
        insert(db, key)
    db.close()
    return url


def profiler(database, new='gpt-6.1-sol'):
    return GptItemProfiler(enabled=True, provider_order='hybrid', openai_api_key='test',
        openai_model='gpt-5', gemini_api_key='test', gemini_model='unchanged-gemini',
        timeout_s=10, max_images=6, image_detail='auto', reasoning_effort='low',
        database_url=database, pricing_model_routing_enabled=True, new_listing_pricing_model=new)


def test_migration_grandfathers_existing_listings_and_new_cohort_is_sticky(database):
    old = resolve_pricing_model(database, 'legacy', 'owner', new_model='gpt-6.1-sol')
    assert old['model'] == 'gpt-5' and old['reason'] == 'legacy_existing_listing'
    new = resolve_pricing_model(database, 'new', 'owner', new_model='gpt-6.1-sol')
    assert new['model'] == 'gpt-6.1-sol'
    assert resolve_pricing_model(database, 'new', 'owner', new_model='gpt-5') == new
    with pytest.raises(ValueError, match='does not belong'):
        resolve_pricing_model(database, 'new', 'different-owner', new_model='gpt-5')


def test_profile_and_reanalysis_use_scoped_models_without_mutating_shared_profiler(database, monkeypatch):
    calls = []
    def fake(self, **kwargs):
        calls.append((self.openai_model, kwargs['condition_grade'], kwargs['refresh_pricing']))
        assert self.gemini_model == 'unchanged-gemini'
        assert self._build_openai_label_ocr_payload(content=[])['model'] == 'gpt-5'
        return GptItemProfileResult(profile={'candidate_brand':'Louis Vuitton'}, enabled=True, called=True)
    monkeypatch.setattr(GptItemProfiler, '_profile_with_saved_identity', fake)
    model = profiler(database)
    for listing_id, condition in [('legacy','New'), ('new','New'), ('new','NewWithTags'), ('legacy','LikeNew')]:
        result = model.profile_item(images=[], brand_name='unknown', category='clothes', item_size='M',
            condition_grade=condition, condition_source='user_input', item_description='Changed copy',
            refresh_pricing=True, listing_id=listing_id, owner_subject='owner')
        assert result.profile['_workflow']['pricing_model_assignment']['listing_id'] == listing_id
    assert [call[0] for call in calls] == ['gpt-5', 'gpt-6.1-sol', 'gpt-6.1-sol', 'gpt-5']
    assert model.openai_model == 'gpt-5' and not model._pricing_assignment_bound


@pytest.mark.parametrize('source_model', ['gpt-5','gpt-6.1-sol'])
def test_duplicate_inherits_source_model_without_new_analysis_and_rebinds_owner(database, source_model):
    assignment = dict(model=source_model, listing_id='source-listing', owner_subject='source-owner')
    analysis = dict(item_profile={'_workflow': {'pricing_model_assignment': assignment}},
        debug={'enrichment':{'gpt_item_profile':{'workflow':{'pricing_model_assignment':copy.deepcopy(assignment)}}}})
    model = profiler(database)
    assert model.accept_reused_pricing_model(listing_id='duplicate', owner_subject='owner', analysis=analysis)
    bound = analysis['item_profile']['_workflow']['pricing_model_assignment']
    assert bound['model'] == source_model and bound['listing_id'] == 'duplicate' and bound['owner_subject'] == 'owner'
    assert analysis['debug']['enrichment']['gpt_item_profile']['workflow']['pricing_model_assignment'] == bound
    assert model.for_listing('duplicate','owner').openai_model == source_model


def test_legacy_cache_without_model_metadata_remains_gpt5_and_existing_pin_is_not_overridden(database):
    model = profiler(database)
    assert model.accept_reused_pricing_model(listing_id='duplicate', owner_subject='owner', analysis={})
    assert model.for_listing('duplicate', 'owner').openai_model == 'gpt-5'
    sol = {'item_profile':{'_workflow':{'pricing_model_assignment':{'model':'gpt-6.1-sol'}}}}
    assert not model.accept_reused_pricing_model(listing_id='legacy', owner_subject='owner', analysis=sol)
    assert model.for_listing('legacy','owner').openai_model == 'gpt-5'


def test_condition_retry_uses_assigned_model_not_shared_default(database, monkeypatch):
    model = profiler(database)
    scoped = model.for_listing('new','owner')
    calls = []
    def price(self, **kwargs):
        calls.append(self.openai_model)
        return {'priced_by':self.openai_model}
    monkeypatch.setattr(GptItemProfiler, '_call_openai_valuation', price)
    result = model.estimate_new_from_like_new(item_profile={'_workflow':{
        'pricing_model_assignment':scoped.pricing_model_assignment}}, reference={'estimated_price':100})
    assert result['priced_by'] == 'gpt-6.1-sol' and calls == ['gpt-6.1-sol']


def test_concurrent_workers_select_same_persisted_model(database):
    results, errors = [], []
    def run(new_model):
        try:
            results.append(resolve_pricing_model(database, 'new', 'owner', new_model=new_model))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=run,args=(name,)) for name in ('gpt-5','gpt-6.1-sol')]
    for thread in threads: thread.start()
    for thread in threads: thread.join(5)
    assert not errors and len(results) == 2
    assert results[0] == results[1]


def test_routing_default_off():
    from app.settings import Settings
    assert Settings.model_fields['gpt_pricing_model_routing_enabled'].default is False
