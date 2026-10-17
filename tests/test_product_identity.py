import copy
import threading

import pytest

from app.db import Database, PersistedImage
from app.gpt_item_profile import GptItemProfiler
from app.product_identity import identity_fingerprint as _fingerprint, resolve_identity as _resolve
from brand.types import ImageInput


def identity_fingerprint(images, **kwargs):
    return _fingerprint(images, listing_id='listing-a', owner_subject='owner-a', **kwargs)


def resolve_identity(*args, **kwargs):
    return _resolve(*args, listing_id='listing-a', owner_subject='owner-a', **kwargs)


def photo(data=b'original'):
    return ImageInput(image_id='id', filename='photo.jpg', content_type='image/jpeg',
                      bytes_data=data, role_hint='full_item')


def identity():
    return dict(category='clothes', candidate_brand='RHODE', candidate_model='Paolo', confidence=.95,
        model_identification={'name': 'Paolo Dress', 'confidence': .95, 'attributes': ['cutout']},
        visual_signatures=['cutout'], listing_description='New dress',
        resale_price_estimate={'estimated_price': 999, 'condition_grade': 'New'})


def profiler(url):
    return GptItemProfiler(enabled=True, provider_order='hybrid,gemini,openai',
        openai_api_key='test', openai_model='test', gemini_api_key='test', gemini_model='test',
        timeout_s=1, max_images=6, image_detail='auto', reasoning_effort='low', database_url=url)


def args(**changes):
    return dict(images=[photo()], brand_name='unknown', category='clothes', item_size='S',
                condition_grade='New', condition_source='user_input', item_description='',
                listing_id='listing-a', owner_subject='owner-a', **changes)


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{tmp_path / 'identity.db'}"
    db = Database(value)
    db.initialize()
    for listing_id, owner in [('listing-a', 'owner-a'), ('listing-b', 'owner-a'), ('listing-c', 'owner-b')]:
        db.insert_listing(listing_id=listing_id, owner_subject=owner, owner_name='Owner', title='Dress',
            mode='trade', category='clothes', brand='RHODE', condition='New', size='S',
            estimated_value=0, city='', image=None, images=[], description='', wants='', tags=[],
            source_item_id=None, analysis=None, status='Review')
    db.close()
    return value


def test_identity_reused_across_workers_and_pricing_refresh_keeps_identity(url, monkeypatch):
    calls = []
    def identify(**kwargs):
        calls.append('identify')
        return identity()
    def price(**kwargs):
        calls.append(('price', kwargs['condition_grade']))
        assert 'resale_price_estimate' not in kwargs['gemini_profile']
        assert 'listing_description' not in kwargs['gemini_profile']
        return dict(candidate_brand='WRONG', model_identification={'name': 'Wrong model'},
                    resale_price_estimate={'estimated_price': 175 if kwargs['condition_grade'] == 'New' else 150,
                                          'condition_grade': kwargs['condition_grade']})
    first, second = profiler(url), profiler(url)
    for model in (first, second):
        monkeypatch.setattr(model, '_call_gemini', identify)
        monkeypatch.setattr(model, '_call_openai_valuation', price)
    one = first.profile_item(**args())
    changed = args()
    changed.update(condition_grade='LikeNew', item_size='M', item_description='Generated listing description', refresh_pricing=True)
    two = second.profile_item(**changed)
    assert calls == ['identify', ('price', 'New'), ('price', 'LikeNew')]
    assert one.profile['candidate_brand'] == two.profile['candidate_brand'] == 'RHODE'
    assert one.profile['model_identification']['name'] == two.profile['model_identification']['name'] == 'Paolo Dress'
    assert two.profile['_workflow']['identity_reuse']['reused'] is True
    assert two.profile['resale_price_estimate']['estimated_price'] == 150


def test_key_ignores_photo_order_but_not_photos_category_brand_or_version():
    def key(images, **kwargs):
        return identity_fingerprint(images, category=kwargs.get('category', 'clothes'),
            brand_name=kwargs.get('brand_name', 'unknown'), model=kwargs.get('model', 'test'))
    original = key([photo(b'a'), photo(b'b')])
    assert original == key([photo(b'b'), photo(b'a')])
    assert original != key([photo(b'a')])
    assert original != key([photo(b'a'), photo(b'c')])
    assert original != key([photo(b'a'), photo(b'b')], category='handbag')
    assert original != key([photo(b'a'), photo(b'b')], brand_name='User corrected brand')
    assert original != key([photo(b'a'), photo(b'b')], model='new-model')


def test_concurrent_jobs_identify_once(url):
    entered, release = threading.Event(), threading.Event()
    calls, results, failures = [], [], []
    def identify():
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return identity()
    def run():
        try:
            results.append(resolve_identity(url, 'same', identify, timeout_s=1))
        except Exception as exc:
            failures.append(exc)
    first, second = threading.Thread(target=run), threading.Thread(target=run)
    first.start()
    assert entered.wait(5)
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert not failures
    assert calls == [1]
    assert sorted(result[1] for result in results) == [False, True]


def test_failed_pricing_retains_identity_without_old_price_or_reidentification(url, monkeypatch):
    model = profiler(url)
    monkeypatch.setattr(model, '_call_gemini', lambda **kwargs: identity())
    monkeypatch.setattr(model, '_call_openai_valuation', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('pricing down')))
    first = model.profile_item(**args())
    assert 'pricing down' in first.error
    assert 'resale_price_estimate' not in first.profile
    monkeypatch.setattr(model, '_call_gemini', lambda **kwargs: pytest.fail('Must not re-identify after pricing failure'))
    assert model.profile_item(**args()).profile['_workflow']['identity_reuse']['reused'] is True


def test_ambiguous_identity_is_not_frozen_and_failed_identification_is_not_saved(url):
    weak = copy.deepcopy(identity())
    weak['model_identification']['confidence'] = .2
    calls = []
    def identify():
        calls.append(1)
        return weak
    resolve_identity(url, 'weak', identify, timeout_s=1)
    resolve_identity(url, 'weak', identify, timeout_s=1)
    assert calls == [1, 1]
    with pytest.raises(RuntimeError):
        resolve_identity(url, 'failed', lambda: (_ for _ in ()).throw(RuntimeError('down')), timeout_s=1)
    assert resolve_identity(url, 'failed', identity, timeout_s=1)[1] is False


def test_verified_legacy_identity_is_seeded_without_prices(url, monkeypatch):
    model = profiler(url)
    model.seed_saved_identity(images=[photo()], category='clothes', brand_name='unknown', profile=identity(),
        listing_id='listing-a', owner_subject='owner-a')
    monkeypatch.setattr(model, '_call_gemini', lambda **kwargs: pytest.fail('Seeded identity must be reused'))
    monkeypatch.setattr(model, '_call_openai_valuation', lambda **kwargs: {'resale_price_estimate': {'estimated_price': 200}})
    result = model.profile_item(**args())
    assert result.profile['_workflow']['identity_reuse']['reused'] is True
    assert result.profile['resale_price_estimate']['estimated_price'] == 200


def test_conflicting_legacy_identity_cannot_replace_canonical(url):
    first = profiler(url)
    original = first.seed_saved_identity(images=[photo()], category='clothes', brand_name='unknown', profile=identity(),
        listing_id='listing-a', owner_subject='owner-a')
    conflicting = identity()
    conflicting['model_identification']['name'] = 'Different dress'
    resolved = profiler(url).seed_saved_identity(images=[photo()], category='clothes', brand_name='unknown', profile=conflicting,
        listing_id='listing-a', owner_subject='owner-a')
    assert resolved == original


def test_new_photos_and_explicit_corrections_trigger_identification(url, monkeypatch):
    model = profiler(url)
    calls = []
    def identify(**kwargs):
        calls.append(1)
        return identity()
    monkeypatch.setattr(model, '_call_gemini', identify)
    monkeypatch.setattr(model, '_call_openai_valuation', lambda **kwargs: {'resale_price_estimate': {'estimated_price': 200}})
    request = args()
    model.profile_item(**request)
    request['images'] = [photo(b'changed')]
    model.profile_item(**request)
    request['brand_name'] = 'User correction'
    model.profile_item(**request)
    request['category'] = 'accessories'
    model.profile_item(**request)
    assert len(calls) == 4


def test_identical_photos_never_reuse_another_listing_or_owners_identity(url, monkeypatch):
    model = profiler(url)
    calls = []
    def identify(**kwargs):
        calls.append(1)
        result = identity()
        result['model_identification']['name'] = f'Dress {len(calls)}'
        return result
    monkeypatch.setattr(model, '_call_gemini', identify)
    monkeypatch.setattr(model, '_call_openai_valuation', lambda **kwargs: {'resale_price_estimate': {'estimated_price': 200}})
    request = args()
    assert model.profile_item(**request).profile['model_identification']['name'] == 'Dress 1'
    request.update(listing_id='listing-b')
    assert model.profile_item(**request).profile['model_identification']['name'] == 'Dress 2'
    request.update(listing_id='listing-c', owner_subject='owner-b')
    assert model.profile_item(**request).profile['model_identification']['name'] == 'Dress 3'
    request.update(listing_id='listing-a', owner_subject='owner-a')
    assert model.profile_item(**request).profile['model_identification']['name'] == 'Dress 1'
    assert len(calls) == 3


def test_owner_spoofing_is_rejected_before_identification(url):
    with pytest.raises(ValueError, match='does not belong'):
        _resolve(url, 'same', lambda: pytest.fail('Must not identify'), timeout_s=1,
                 listing_id='listing-a', owner_subject='owner-b')


def test_scope_is_enforced_in_query_even_if_fingerprint_is_reused(url):
    first, _ = _resolve(url, 'same', identity, timeout_s=1, listing_id='listing-a', owner_subject='owner-a')
    different = identity()
    different['model_identification']['name'] = 'Other listing'
    second, reused = _resolve(url, 'same', lambda: different, timeout_s=1,
                              listing_id='listing-b', owner_subject='owner-a')
    assert reused is False
    assert first['model_identification']['name'] != second['model_identification']['name']


def test_direct_analysis_without_listing_does_not_persist_identity(url, monkeypatch):
    model = profiler(url)
    calls = []
    def identify(**kwargs):
        calls.append(1)
        return identity()
    monkeypatch.setattr(model, '_call_gemini_openai_hybrid', identify)
    request = args()
    request.pop('listing_id')
    model.profile_item(**request)
    model.profile_item(**request)
    assert len(calls) == 2
    db = Database(url)
    assert db.fetchone('SELECT COUNT(*) FROM listing_product_identities')[0] == 0
    db.close()


def test_full_analysis_reuse_requires_same_listing_owner_and_job(url):
    db = Database(url)
    for listing_id, item_id in [('listing-a', 'item-a'), ('listing-b', 'item-b')]:
        db.insert_item(item_id)
        db.insert_image(PersistedImage(image_id=item_id, item_id=item_id, filename='photo.jpg',
            storage_uri='local://photo.jpg', role_hint='full_item', content_hash='identical'))
        db.insert_analysis('analysis-' + item_id, item_id, {'item_id': item_id, 'category': 'clothes',
            '_original_photo_hashes': ['identical'],
            'brand': {'name': 'RHODE', 'confidence': .95, 'evidence': 'label'},
            'condition': {'grade': 'New', 'confidence': 1}})
        db.create_listing_analysis_job(job_id='job-' + item_id, listing_id=listing_id, owner_subject='owner-a', max_attempts=2)
        db.update_listing_analysis_job(job_id='job-' + item_id, owner_subject='owner-a', status='succeeded',
                                       result_item_id=item_id, completed=True)
    match = db.find_recent_analysis_by_image_hashes(['identical'], listing_id='listing-a', owner_subject='owner-a')
    assert match['item_id'] == 'item-a'
    assert db.find_recent_analysis_by_image_hashes(['identical'], listing_id='listing-a', owner_subject='owner-b') is None
    assert db.find_recent_analysis_by_image_hashes(['identical'], listing_id='listing-c', owner_subject='owner-b') is None
    # Even pointing another listing at the previous item must not borrow its job.
    db.execute("UPDATE listings SET source_item_id=? WHERE listing_id=?", ('item-a', 'listing-c'))
    db.link_analysis_item('item-a', 'listing-c', 'owner-b')
    db.commit()
    assert db.find_recent_analysis_by_image_hashes(['identical'], listing_id='listing-c', owner_subject='owner-b') is None
    db.close()


@pytest.mark.parametrize('target', [['a'], ['a', 'b', 'c'], ['a', 'different'], ['b', 'b']])
def test_global_analysis_reuse_requires_complete_exact_photo_evidence(url, target):
    db = Database(url)
    db.insert_item('priced-item')
    db.insert_analysis('evidence', 'priced-item', {'item_id': 'priced-item', 'category': 'clothes',
        'brand': {'name': 'RHODE', 'confidence': .95, 'evidence': 'label'},
        'condition': {'grade': 'New', 'confidence': 1}, 'user_condition': 'New',
        '_original_photo_hashes': ['a', 'b'], '_analysis_input_context': {'item_description': ''}})
    assert db.find_recent_analysis_by_image_hashes(target, condition_grade='New', category='clothes', item_description='') is None
    assert db.find_recent_analysis_by_image_hashes(['b', 'a'], condition_grade='New', category='clothes', item_description='')['item_id'] == 'priced-item'
    assert db.find_recent_analysis_by_image_hashes(['a', 'b'], condition_grade='LikeNew', category='clothes', item_description='') is None
    assert db.find_recent_analysis_by_image_hashes(['a', 'b'], condition_grade='New', category='shoes', item_description='') is None
    assert db.find_recent_analysis_by_image_hashes(['a', 'b'], condition_grade='New', brand_name='Corrected brand', item_description='') is None
    assert db.find_recent_analysis_by_image_hashes(['a', 'b'], condition_grade='New', item_description='Different product facts') is None
    db.close()


def test_legacy_candidate_uses_its_original_analysis_refs_not_later_item_images(url):
    db = Database(url)
    db.insert_item('legacy-item')
    for name in ('old-photo', 'new-photo', 'ai-photo'):
        db.insert_image(PersistedImage(image_id=name, item_id='legacy-item', filename=name,
            storage_uri='local://' + name, role_hint='ai_mannequin' if name == 'ai-photo' else 'full_item', content_hash=name))
    db.insert_analysis('legacy', 'legacy-item', {'item_id': 'legacy-item', 'category': 'clothes',
        'brand': {'name': 'RHODE', 'confidence': .95, 'evidence': 'label'},
        'condition': {'grade': 'New', 'confidence': 1},
        'uploaded_images': [{'image_id': 'old-photo'}]})
    assert db.find_recent_analysis_by_image_hashes(['old-photo'])['item_id'] == 'legacy-item'
    assert db.find_recent_analysis_by_image_hashes(['new-photo']) is None
    assert db.find_recent_analysis_by_image_hashes(['old-photo', 'new-photo', 'ai-photo']) is None
    db.close()
