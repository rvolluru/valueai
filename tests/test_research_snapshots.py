import copy
import json
import threading

import pytest

from app.controlled_research import (candidate_rejection, collect_research, research_payload,
    research_plan, resolve_snapshot, snapshot_key)
from app.db import Database
from app.gpt_item_profile import GptItemProfiler

IDENTITY = dict(candidate_brand='Louis Vuitton', candidate_model='Monogram Jacquard Fleece Jacket', category='clothes')
SCOPE = dict(owner_subject='owner-a', listing_id='listing-a', photo_fingerprint='photos-a')
URL = 'https://poshmark.com/listing/louis-vuitton-fleece-jacket-123'


def candidate():
    return dict(url=URL, brand='Louis Vuitton', model='Monogram Fleece Jacket',
        title='Louis Vuitton Monogram Fleece Jacket', product_type='jacket', material='fleece',
        condition='Good', price=2400, currency='USD', price_type='asking', price_quote='$2,400',
        summary='Louis Vuitton fleece jacket listed for $2,400.', variant_differences='Similar model')


def research_response(payload, timeout):
    plan = json.loads(payload['input'])['site_plan']
    rows = [candidate()] if plan['site'] == 'Poshmark' else []
    raw = dict(output=[dict(type='web_search_call', action=dict(type='search', query=plan['queries'][0],
        sources=[dict(url=r['url'], title=r['title']) for r in rows]))])
    return raw, dict(coverage_notes='Observed results', candidates=rows)


def snapshot():
    return collect_research(IDENTITY, 'research-model', research_response, 10)


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path / 'research.db'}"
    db = Database(url)
    db.initialize()
    db.insert_listing(listing_id='listing-a', owner_subject='owner-a', owner_name='Owner', title='Jacket',
        mode='trade', category='clothes', brand='Louis Vuitton', condition='New', size='M',
        estimated_value=0, city='', image=None, images=[], description='', wants='', tags=[],
        source_item_id=None, analysis=None, status='Review')
    db.close()
    return url


@pytest.mark.parametrize('model,product', [('Monogram Fleece Jacket','jacket'),
    ('Paolo Silk Dress','dress'), ('Leather Ankle Boots','boot'), ('Marmont Shoulder Bag','bag')])
def test_plan_and_validation_generalize_beyond_denim(model, product):
    identity = dict(IDENTITY, candidate_model=model)
    plan = research_plan(identity)
    assert len(plan) == 8
    assert 'denim' not in json.dumps(plan)
    assert plan == research_plan(dict(identity, user_condition='NewWithTags', size='XL'))
    payload = research_payload(plan[1], identity, 'gpt-5')
    assert 'workwear' not in json.dumps(payload)
    row = dict(candidate(), model=model, title=model, product_type=product, summary=model)
    assert candidate_rejection(row, dict(domains=['poshmark.com'], role='resale'), identity, {URL}) is None


def test_scope_and_identity_invalidation_but_not_condition():
    key = snapshot_key(SCOPE, IDENTITY)
    assert key == snapshot_key(SCOPE, dict(IDENTITY, user_condition='NewWithTags', visual_condition_assessment={'wear':'none'}))
    for field in ('owner_subject', 'listing_id', 'photo_fingerprint'):
        assert key != snapshot_key(dict(SCOPE, **{field:'different'}), IDENTITY)
    assert key != snapshot_key(SCOPE, dict(IDENTITY, candidate_brand='Gucci'))
    assert key != snapshot_key(SCOPE, dict(IDENTITY, candidate_model='Silk Dress'))


def test_persistent_reuse_expiry_and_photo_invalidation(database):
    calls = []
    def collect(remaining):
        calls.append(1)
        return snapshot()
    one, reused = resolve_snapshot(database, SCOPE, IDENTITY, collect, ttl_s=100, timeout_s=10)
    assert not reused
    two, reused = resolve_snapshot(database, SCOPE, dict(IDENTITY, user_condition='NewWithTags'), collect, ttl_s=100, timeout_s=10)
    assert reused and one == two and len(calls) == 1
    changed, reused = resolve_snapshot(database, dict(SCOPE, photo_fingerprint='new-photo'), IDENTITY, collect, ttl_s=100, timeout_s=10)
    assert not reused and changed['snapshot_id'] != one['snapshot_id']
    db = Database(database)
    db.execute('UPDATE pricing_research_snapshots SET created_at=?', ('2000-01-01T00:00:00+00:00',))
    db.commit()
    db.close()
    newer, reused = resolve_snapshot(database, SCOPE, IDENTITY, collect, ttl_s=100, timeout_s=10)
    assert not reused and newer['snapshot_id'] != one['snapshot_id']


def test_owner_guard_and_no_runtime_schema_creation(database):
    with pytest.raises(ValueError, match='does not belong'):
        resolve_snapshot(database, dict(SCOPE, owner_subject='other'), IDENTITY,
            lambda _: pytest.fail('Must not research'), ttl_s=100, timeout_s=10)


def test_single_flight_across_workers(database):
    entered, release = threading.Event(), threading.Event()
    calls, results, errors = [], [], []
    def collect(_):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return snapshot()
    def run():
        try:
            results.append(resolve_snapshot(database, SCOPE, IDENTITY, collect, ttl_s=100, timeout_s=5))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=run) for _ in range(2)]
    threads[0].start()
    assert entered.wait(3)
    threads[1].start()
    release.set()
    for thread in threads:
        thread.join(5)
    assert not errors and calls == [1]
    assert sorted(r[1] for r in results) == [False, True]


def test_failed_or_empty_research_is_not_cached(database):
    calls = []
    def collect(_):
        calls.append(1)
        value = snapshot()
        value['research'][0]['status'] = 'failed'
        return value
    for _ in range(2):
        result, reused = resolve_snapshot(database, SCOPE, IDENTITY, collect, ttl_s=100, timeout_s=5)
        assert not reused and 'snapshot_id' not in result
    assert len(calls) == 2


def test_missing_snapshot_migration_fails_without_runtime_ddl(database):
    import sqlite3
    db = Database(database)
    db.execute('DROP TABLE pricing_research_snapshots')
    db.commit()
    db.close()
    with pytest.raises(sqlite3.OperationalError, match='no such table'):
        resolve_snapshot(database, SCOPE, IDENTITY, lambda _: pytest.fail('No runtime migration'), ttl_s=100, timeout_s=5)


def test_research_conflicting_prices_are_excluded_and_source_roles_separate():
    from app.controlled_research import shared_evidence
    row = candidate()
    raw = dict(output=[dict(type='web_search_call', action=dict(sources=[dict(url=URL)]))])
    research = dict(status='returned', plan=dict(site='Poshmark', domains=['poshmark.com'], role='resale'),
        data=dict(candidates=[row, dict(row, price=2500, price_quote='$2500')]), raw_response=raw)
    evidence = shared_evidence(dict(identity=IDENTITY, research=[research]))
    assert not evidence['comparables']
    assert evidence['exclusions'][0]['reason'] == 'conflicting_extracted_price_facts'
    assert candidate_rejection(dict(row, price_type='retail'), research['plan'], IDENTITY, {URL}) == 'wrong_price_type_for_source_role'


def profiler(database):
    return GptItemProfiler(enabled=True, provider_order='hybrid', openai_api_key='test', openai_model='gpt-5',
        gemini_api_key='test', gemini_model='test', timeout_s=10, max_images=6, image_detail='auto',
        reasoning_effort='low', database_url=database, controlled_research_enabled=True)


@pytest.mark.parametrize('mode', ['valid', 'changed_price', 'new_url'])
def test_runtime_no_search_valuation_reuses_snapshot_across_conditions(database, monkeypatch, mode):
    model = profiler(database)
    calls = []
    def request(payload, timeout):
        calls.append(copy.deepcopy(payload))
        if payload.get('tools'):
            return research_response(payload, timeout)
        assert 'include' not in payload
        text = payload['input'][0]['content'][-1]['text']
        evidence = json.loads(text.split('\n',1)[1])
        row = {k:evidence[0][k] for k in ('url','brand','model','condition','price','currency','price_type')}
        row.update(match_type='related', variant_match='unconfirmed', match_evidence='Same-brand fleece jacket',
            similarity_basis='Similar construction', adjustment_explanation='Adjust for condition')
        if mode == 'changed_price':
            row['price'] = 1
        if mode == 'new_url':
            row['url'] = 'https://poshmark.com/listing/invented'
        return dict(output=[]), dict(pricing_comparables=[row], grounding_sources=[],
            resale_price_estimate=dict(estimated_price=2700, condition_grade='New', references=[dict(url=row['url'])]),
            retail_price_estimate=dict(estimated_price=None, references=[]), resale_price_breakdown=[])
    monkeypatch.setattr(model, '_research_request', request)
    for condition in ('New','NewWithTags'):
        value = model._call_openai_valuation(content=[], gemini_profile=IDENTITY,
            condition_grade=condition, research_scope=SCOPE)
        policy = value['pricing_evidence_policy']
        assert policy['status'] == ('qualified' if mode == 'valid' else 'needs_review')
    assert len([p for p in calls if p.get('tools')]) == 8
    assert len(calls) == 10
    assert policy['controlled_research']['reused']


def test_feature_default_off_and_requires_scope_when_enabled(database):
    model = profiler(database)
    with pytest.raises(ValueError, match='scoped snapshot'):
        model._call_openai_valuation(content=[], gemini_profile=IDENTITY, condition_grade='New')
    from app.settings import Settings
    assert Settings().gpt_controlled_research_enabled is False
