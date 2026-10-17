import itertools
import threading
from types import SimpleNamespace

import pytest

from app.db import Database
from app import listing_pipeline as pipeline
from app.pipeline_results import merge_result, photo_signature, StalePipelineResult


def setup_pipeline(tmp_path):
    settings = SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'pipeline.db'}",
        image_staging_enabled=True, mannequin_image_generation_enabled=True, gemini_api_key='test',
        listing_mannequin_timeout_s=5, listing_staging_timeout_s=5)
    db = Database(settings.database_url)
    db.initialize()
    db.insert_listing(listing_id='listing', owner_subject='owner', owner_name='Owner', title='Shorts',
        mode='trade', category='clothes', brand='', condition='New', size='S', estimated_value=0,
        city='', image='/v1/images/original', images=['/v1/images/original'], description='',
        wants='', tags=[], source_item_id='input', analysis={}, status='Analyzing')
    db.create_listing_analysis_job(job_id='job', listing_id='listing', owner_subject='owner', max_attempts=2)
    listing = db.get_listing_by_id('listing')
    snapshot = dict(job_id='job', listing_id='listing', owner_subject='owner', listing=listing,
        photo_signature=photo_signature(listing), files=[], inputs=dict(category='clothes', debug=False,
        stage_images_after_analysis=True))
    db.create_pipeline_components('job', snapshot)
    return settings, db, snapshot


@pytest.mark.parametrize('order', list(itertools.permutations(['pricing', 'mannequin', 'staging'])))
def test_result_merge_orders_preserve_other_components_and_user_edits(tmp_path, order):
    _, db, snapshot = setup_pipeline(tmp_path)
    db.execute("UPDATE listings SET title='My edited title' WHERE listing_id='listing'")
    db.commit()
    results = {
        'pricing': dict(analysis={'item_id': 'priced', 'debug': {}}, source_item_id='priced',
            estimated_value=200, title='AI title', status='Review'),
        'mannequin': dict(image_id='mannequin', image_url='/v1/images/mannequin', synthetic=True),
        'staging': [dict(source_image_url='/v1/images/original', image_url='/v1/images/staged')],
    }
    for component in order:
        merge_result(db, snapshot, component, results[component])
    listing = db.get_listing_by_id('listing')
    assert listing['title'] == 'My edited title'
    assert listing['estimated_value'] == 200
    assert listing['status'] == 'Review'
    assert listing['analysis']['generated_assets'][0]['image_id'] == 'mannequin'
    assert listing['analysis']['presentation_assets'][0]['image_url'] == '/v1/images/staged'
    assert listing['image'] == '/v1/images/staged'
    assert photo_signature(listing) == snapshot['photo_signature']
    assert len(listing['listed_images']) == 2


@pytest.mark.parametrize('change', ['photos', 'job', 'condition'])
def test_rejects_stale_result(tmp_path, change):
    _, db, snapshot = setup_pipeline(tmp_path)
    if change == 'job':
        db.create_listing_analysis_job(job_id='new-job', listing_id='listing', owner_subject='owner', max_attempts=2)
    else:
        field, value = ('images_json', '["/v1/images/new"]') if change == 'photos' else ('condition', 'LikeNew')
        db.execute(f'UPDATE listings SET {field}=? WHERE listing_id=?', (value, 'listing'))
        db.commit()
    with pytest.raises(StalePipelineResult):
        merge_result(db, snapshot, 'pricing', dict(analysis={}, estimated_value=200, source_item_id='priced'))
    assert db.get_listing_by_id('listing')['estimated_value'] == 0


def test_branches_start_in_parallel_and_resume_does_not_repeat_pricing(tmp_path, monkeypatch):
    settings, db, snapshot = setup_pipeline(tmp_path)
    from app import main
    barrier = threading.Barrier(3)
    counts = dict(pricing=0, mannequin=0, staging=0)
    def price(component_db, *args):
        counts['pricing'] += 1
        barrier.wait(5)
        component_db.update_listing_analysis_job(job_id='job', owner_subject='owner', status='succeeded',
            result_item_id='priced', completed=True)
        return 'succeeded', 1
    async def mannequin(*args):
        counts['mannequin'] += 1
        barrier.wait(5)
        raise RuntimeError('image provider failed')
    async def staging(**kwargs):
        counts['staging'] += 1
        barrier.wait(5)
        return []
    monkeypatch.setattr(pipeline, '_load_originals', lambda *args: [])
    monkeypatch.setattr(pipeline, '_pricing', price)
    monkeypatch.setattr(pipeline, '_mannequin', mannequin)
    monkeypatch.setattr(main, '_run_listing_image_staging_job', staging)
    # Only the first image attempt synchronizes with the other branches.
    async def retrying_mannequin(*args):
        if counts['mannequin'] == 0:
            return await mannequin(*args)
        counts['mannequin'] += 1
        raise RuntimeError('image provider failed again')
    monkeypatch.setattr(pipeline, '_mannequin', retrying_mannequin)
    args = dict(settings=settings, job_id='job', listing_id='listing', owner_subject='owner',
        category='clothes', item_size='S', user_condition='New', item_description='', debug=False,
        valuation_service=None, gpt_item_profiler=None)
    pipeline.run_listing_pipeline(**args)
    assert counts == dict(pricing=1, mannequin=2, staging=1)
    assert db.get_listing_analysis_job('job')['status'] == 'succeeded'
    states = {row['component']: row['status'] for row in db.list_pipeline_components('job')}
    assert states == dict(pricing='succeeded', mannequin='failed', staging='skipped')
    db.set_pipeline_component('job', 'staging', 'running', 1)
    async def resumed_staging(**kwargs):
        counts['staging'] += 1
        return []
    monkeypatch.setattr(main, '_run_listing_image_staging_job', resumed_staging)
    pipeline.run_listing_pipeline(**args)
    assert counts == dict(pricing=1, mannequin=2, staging=2)
    assert len(db.listing_pipeline_states(['listing'], 'owner')['listing']) == 3
    assert db.listing_pipeline_states(['listing'], 'other') == {}


def test_frozen_photos_are_verified(tmp_path, monkeypatch):
    settings, db, snapshot = setup_pipeline(tmp_path)
    from app import main
    snapshot['files'] = [dict(source_url='/v1/images/original', content_hash='wrong', filename='photo.jpg')]
    monkeypatch.setattr(main, '_image_file_from_listing_url', lambda **kwargs: {'data': b'changed'})
    with pytest.raises(ValueError, match='Frozen original'):
        pipeline._load_originals(db, snapshot, settings)


def test_pricing_completes_while_optional_images_are_still_running(tmp_path, monkeypatch):
    settings, db, snapshot = setup_pipeline(tmp_path)
    from app import main
    images_started = threading.Barrier(2)
    priced, release_images = threading.Event(), threading.Event()
    failures = []
    def price(component_db, *args):
        component_db.update_listing_analysis_job(job_id='job', owner_subject='owner', status='succeeded',
            result_item_id='priced', completed=True)
        priced.set()
        return 'succeeded', 1
    async def mannequin(*args):
        images_started.wait(5)
        assert release_images.wait(5)
    async def staging(**kwargs):
        images_started.wait(5)
        assert release_images.wait(5)
        return []
    monkeypatch.setattr(pipeline, '_load_originals', lambda *args: [])
    monkeypatch.setattr(pipeline, '_pricing', price)
    monkeypatch.setattr(pipeline, '_mannequin', mannequin)
    monkeypatch.setattr(main, '_run_listing_image_staging_job', staging)
    def run():
        try:
            pipeline.run_listing_pipeline(settings=settings, job_id='job', listing_id='listing',
                owner_subject='owner', category='clothes', item_size='S', user_condition='New',
                item_description='', debug=False, valuation_service=None, gpt_item_profiler=None)
        except Exception as exc:
            failures.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert priced.wait(5)
        assert db.get_listing_analysis_job('job')['status'] == 'succeeded'
        assert thread.is_alive()
    finally:
        release_images.set()
        thread.join(5)
    assert not failures
    assert not thread.is_alive()


def test_old_full_result_cache_cannot_override_shared_identity(tmp_path, monkeypatch):
    settings, db, snapshot = setup_pipeline(tmp_path)
    from app import main
    canonical = {'candidate_brand': 'RHODE', 'model_identification': {'name': 'Paolo Dress'}}
    cached = {'analysis': {'item_profile': {'candidate_brand': 'RHODE', 'model_identification': {'name': 'Generic dress'}}}}
    monkeypatch.setattr(main, '_reuse_recent_analysis_for_listing', lambda **kwargs: cached)
    called = []
    def price(**kwargs):
        called.append('fresh pricing')
        db.update_listing_analysis_job(job_id='job', owner_subject='owner', status='succeeded',
            result_item_id='priced', completed=True)
    monkeypatch.setattr(main, '_run_listing_analysis_job_threaded', price)
    model = SimpleNamespace(seed_saved_identity=lambda **kwargs: canonical)
    assert pipeline._pricing(db, snapshot, [{'data': b'original'}], settings, None, model)[0] == 'succeeded'
    assert called == ['fresh pricing']


def test_pipeline_rejects_partial_photo_resolution_before_cache_or_models(tmp_path, monkeypatch):
    settings, db, snapshot = setup_pipeline(tmp_path)
    from app import main
    monkeypatch.setattr(main, '_collect_listing_analysis_files', lambda **kwargs: [])
    with pytest.raises(ValueError, match='Not all current'):
        pipeline._prepare_inputs(db, snapshot['listing'], None, settings, 'job', {})


def test_current_bytes_not_stale_source_item_are_used_for_reuse(tmp_path, monkeypatch):
    settings, db, snapshot = setup_pipeline(tmp_path)
    from app import main
    captured = []
    def lookup(hashes, **kwargs):
        captured.extend(hashes)
        return None
    monkeypatch.setattr(db, 'find_recent_analysis_by_image_hashes', lookup)
    import hashlib
    assert main._reuse_recent_analysis_for_listing(db=db, listing_id='listing', owner_subject='owner',
        current=snapshot['listing'], persist=False, files=[{'data': b'new-photo'}]) is None
    assert captured == [hashlib.sha256(b'new-photo').hexdigest()]


def test_same_filename_and_size_do_not_drop_different_photos(monkeypatch):
    from app import main
    files = iter([{'data': b'aaa', 'filename': 'same.jpg'}, {'data': b'bbb', 'filename': 'same.jpg'}])
    monkeypatch.setattr(main, '_image_file_from_listing_url', lambda **kwargs: next(files))
    result = main._collect_listing_analysis_files(db=None, settings=SimpleNamespace(max_images_per_request=6),
        listing={'images': ['/v1/images/a', '/v1/images/b']})
    assert len(result) == 2
