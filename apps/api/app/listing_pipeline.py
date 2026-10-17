"""Parallel, independently checkpointed pricing and optional image components."""
import asyncio
import copy
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from .analysis_execution import guard_analysis_job, recover_analysis_success
from .db import Database, PersistedImage
from .logging_utils import log_json
from .pipeline_results import StalePipelineResult, merge_result, original_urls, photo_key, photo_signature

TERMINAL = {'succeeded', 'failed', 'skipped', 'superseded'}


def _prepare_inputs(db, current, files, settings, job_id, inputs):
    from . import main
    if files is None:
        files = main._collect_listing_analysis_files(db=db, settings=settings, listing=current)
        if sorted(photo_key(entry.get('source_url')) for entry in files) != photo_signature(current):
            raise ValueError('Not all current original photos could be read; refusing partial analysis')
    if not files:
        raise ValueError('No readable original photos for pipeline')
    storage = main.build_storage(settings)
    input_item = current.get('source_item_id') or f'pipeline-input-{uuid.uuid4()}'
    if any(not entry.get('source_url') for entry in files):
        input_item = f'pipeline-input-{uuid.uuid4()}'
        db.insert_item(input_item)
    descriptors = []
    for entry in files:
        source = entry.get('source_url')
        digest = hashlib.sha256(entry['data']).hexdigest()
        if not source:
            image_id = str(uuid.uuid4())
            filename = image_id + main._upload_extension(entry.get('filename'), entry.get('content_type'))
            uri = storage.save_upload(item_id=input_item, filename=filename, content_type=entry.get('content_type') or 'image/jpeg', data=entry['data'])
            db.insert_image(PersistedImage(image_id=image_id, item_id=input_item, storage_uri=uri,
                filename=entry.get('filename') or filename, role_hint=entry.get('role_hint') or 'full_item', content_hash=digest))
            source = f'/v1/images/{image_id}'
        descriptors.append({'source_url': source, 'content_hash': digest,
                            'filename': entry.get('filename') or 'photo.jpg'})
    sources = [entry['source_url'] for entry in descriptors]
    # Multipart legacy clients can supply new originals directly. Bind them to
    # this run before parallel work starts; never infer them from generated assets.
    if sorted(photo_key(url) for url in sources) != photo_signature(current):
        old_signature = photo_signature(current)
        def adopt(listing):
            latest = db.get_latest_listing_analysis_job(listing['listing_id'], listing['owner_subject'])
            if not latest or latest['job_id'] != job_id or photo_signature(listing) != old_signature:
                return None
            import json
            return {'images_json': json.dumps(sources), 'image': sources[0], 'source_item_id': input_item}
        if not db.mutate_pipeline_listing(current['listing_id'], current['owner_subject'], adopt):
            raise StalePipelineResult('Photos changed while preparing pipeline inputs')
        current = db.get_listing_by_id(current['listing_id'])
        db.link_analysis_item(input_item, current['listing_id'], current['owner_subject'], job_id)
    return db.create_pipeline_components(job_id, {
        'job_id': job_id, 'listing_id': current['listing_id'], 'owner_subject': current['owner_subject'],
        'listing': current, 'photo_signature': photo_signature(current), 'files': descriptors, 'inputs': inputs,
    })


def _load_originals(db, snapshot, settings):
    from . import main
    files = []
    for index, descriptor in enumerate(snapshot['files']):
        entry = main._image_file_from_listing_url(db=db, settings=settings, url=descriptor['source_url'], index=index,
                                                  source_item_id=snapshot['listing'].get('source_item_id'))
        if not entry or hashlib.sha256(entry['data']).hexdigest() != descriptor['content_hash']:
            raise ValueError('Frozen original photo is unavailable or changed; refusing to substitute another photo')
        entry['filename'] = descriptor['filename']
        files.append(entry)
    db.commit()
    return files


def _pricing(db, snapshot, files, settings, valuation_service, gpt_item_profiler):
    from . import main
    args = snapshot['inputs']
    job = recover_analysis_success(db, snapshot['job_id'], snapshot['owner_subject'])
    if job['status'] == 'succeeded':
        return 'succeeded', job['attempts']
    # Seed unchanged, previously linked evidence on upgrade. Hashes must match
    # the actual originals, not merely the listing's current source-item pointer.
    previous = snapshot['listing'].get('analysis') or {}
    correction = args.get('brand_override') or (previous.get('user_corrections') or {}).get('brand')
    canonical = None
    identity_images = []
    if hasattr(gpt_item_profiler, 'seed_saved_identity'):
        from brand.types import ImageInput
        identity_images = [ImageInput(image_id=str(i), filename=entry.get('filename') or 'photo.jpg',
            content_type=entry.get('content_type') or 'image/jpeg', bytes_data=entry['data'], role_hint='full_item')
            for i, entry in enumerate(files)]
    if (hasattr(gpt_item_profiler, 'seed_saved_identity') and previous.get('item_id')
            and db.item_is_linked_to_listing(previous['item_id'], snapshot['listing_id'], snapshot['owner_subject'])):
        records = db.list_image_records_for_item(previous['item_id'], limit=20)
        old_hashes = sorted(record.get('content_hash') or '' for record in records
                            if not str(record.get('role_hint') or '').startswith('ai_'))
        hashes = sorted(hashlib.sha256(entry['data']).hexdigest() for entry in files)
        old_correction = (previous.get('user_corrections') or {}).get('brand')
        if (hashes and hashes == old_hashes and args['category'] == previous.get('category')
                and (not args.get('brand_override') or args['brand_override'] == old_correction)):
            db.commit()
            canonical = gpt_item_profiler.seed_saved_identity(
                images=identity_images, category=args['category'], brand_name=correction or 'unknown',
                profile=previous.get('item_profile') or {},
                listing_id=snapshot['listing_id'], owner_subject=snapshot['owner_subject'])
    cached = None
    if not args.get('force_fresh_analysis') and not args.get('brand_override'):
        cached = main._reuse_recent_analysis_for_listing(db=db, listing_id=snapshot['listing_id'],
            owner_subject=snapshot['owner_subject'], current=snapshot['listing'], persist=False, files=files)
    if cached and not canonical and identity_images:
        canonical = gpt_item_profiler.seed_saved_identity(images=identity_images,
            category=args['category'], brand_name=correction or 'unknown',
            profile=cached['analysis'].get('item_profile') or {},
            listing_id=snapshot['listing_id'], owner_subject=snapshot['owner_subject'])
    if cached and canonical:
        profile = cached['analysis'].get('item_profile') or {}
        def identity_name(value):
            return (str(value.get('candidate_brand') or '').strip().casefold(),
                    str((value.get('model_identification') or {}).get('name') or '').strip().casefold())
        if identity_name(profile) != identity_name(canonical):
            cached = None
    if cached:
        cached['analysis'].setdefault('debug', {})['analysis_execution'] = {
            'job_id': snapshot['job_id'], 'listing_id': snapshot['listing_id']}
        cached['source_item_id'] = cached.get('source_item_id') or snapshot['listing'].get('source_item_id')
        merge_result(db, snapshot, 'pricing', cached)
        db.update_listing_analysis_job(job_id=snapshot['job_id'], owner_subject=snapshot['owner_subject'],
            status='succeeded', stage='reused', result_item_id=cached['source_item_id'], attempts=0, error='', completed=True)
        return 'succeeded', 0
    main._run_listing_analysis_job_threaded(
        listing_id=snapshot['listing_id'], owner_subject=snapshot['owner_subject'], files=files,
        category=args['category'], item_size=args.get('item_size'), user_condition=args.get('user_condition'),
        item_description=args.get('item_description'), brand_override=correction, debug=args['debug'],
        settings=settings, valuation_service=valuation_service, gpt_item_profiler=gpt_item_profiler,
        job_id=snapshot['job_id'], pipeline_snapshot=snapshot, stage_images_after_analysis=False,
    )
    job = db.get_listing_analysis_job(snapshot['job_id'], snapshot['owner_subject'])
    if job['status'] not in {'succeeded', 'superseded'}:
        raise RuntimeError(job.get('error') or 'Pricing analysis failed')
    return job['status'], job['attempts']


async def _mannequin(db, snapshot, files, settings):
    from . import main
    baseline = snapshot['listing']
    item_id = baseline.get('source_item_id') or f"pipeline-{snapshot['job_id']}"
    db.insert_item(item_id)
    asset = await main._generate_mannequin_listing_asset(files=files, category=snapshot['inputs']['category'],
        title=baseline.get('title') or '', description=baseline.get('description') or '', item_id=item_id,
        settings=settings, db=db, storage=main.build_storage(settings), raise_on_error=True)
    if not asset:
        raise RuntimeError('No safe mannequin preview produced; see mannequin generation logs')
    merge_result(db, snapshot, 'mannequin', asset)


def _run_component(component, snapshot, files, settings, valuation_service, gpt_item_profiler):
    from . import main
    db = Database(settings.database_url)
    job_id = snapshot['job_id']
    try:
        state = next(row for row in db.list_pipeline_components(job_id) if row['component'] == component)
        if state['status'] in TERMINAL:
            return
        current = db.get_listing_by_id(snapshot['listing_id'])
        checkpoint = (((current or {}).get('analysis') or {}).get('debug') or {}).get('pipeline_results', {}).get(component, {})
        if checkpoint.get('job_id') == job_id and checkpoint.get('status') == 'succeeded':
            db.set_pipeline_component(job_id, component, 'succeeded', state['attempts'])
            return
        enabled = (component == 'pricing' or
                   component == 'staging' and snapshot['inputs']['stage_images_after_analysis'] and settings.image_staging_enabled or
                   component == 'mannequin' and settings.mannequin_image_generation_enabled and settings.gemini_api_key
                   and snapshot['inputs']['category'] in {'clothes', 'handbag'})
        if not enabled:
            db.set_pipeline_component(job_id, component, 'skipped', 0)
            return
        # Pricing has its own two-attempt loop. Do not wrap it in another retry loop.
        max_attempts = 1 if component == 'pricing' else 2
        start_attempt = (1 if component == 'pricing' else
                         max(1, state['attempts']) if state['status'] == 'running' else state['attempts'] + 1)
        for attempt in range(start_attempt, max_attempts + 1):
            db.set_pipeline_component(job_id, component, 'running', attempt)
            try:
                if component == 'pricing':
                    status, attempts = _pricing(db, snapshot, files, settings, valuation_service, gpt_item_profiler)
                elif component == 'mannequin':
                    asyncio.run(asyncio.wait_for(_mannequin(db, snapshot, files, settings), timeout=settings.listing_mannequin_timeout_s))
                    status, attempts = 'succeeded', attempt
                else:
                    result = asyncio.run(asyncio.wait_for(main._run_listing_image_staging_job(
                        listing_id=snapshot['listing_id'], owner_subject=snapshot['owner_subject'], files=files,
                        settings=settings, pipeline_snapshot=snapshot), timeout=settings.listing_staging_timeout_s))
                    status, attempts = ('succeeded' if result else 'skipped'), attempt
                db.set_pipeline_component(job_id, component, status, attempts)
                return
            except StalePipelineResult as exc:
                db.set_pipeline_component(job_id, component, 'superseded', attempt, str(exc))
                return
            except Exception as exc:
                error = str(exc) or type(exc).__name__
                log_json('listing_pipeline_component_failed', job_id=job_id, listing_id=snapshot['listing_id'],
                         component=component, attempt=attempt, error=error[:1000])
                status = 'retrying' if attempt < max_attempts else 'failed'
                db.set_pipeline_component(job_id, component, status, attempt, error)
    finally:
        db.close()


@guard_analysis_job(resume_components=True)
def run_listing_pipeline(*, listing_id, owner_subject, category, item_size, user_condition, item_description,
                         debug, settings, valuation_service, gpt_item_profiler, job_id, files=None,
                         stage_images_after_analysis=False, brand_override=None, force_fresh_analysis=False):
    db = Database(settings.database_url)
    try:
        snapshot = db.get_pipeline_inputs(job_id)
        if not snapshot:
            current = db.get_listing_by_id(listing_id)
            latest = db.get_latest_listing_analysis_job(listing_id, owner_subject)
            if not current or current['owner_subject'] != owner_subject:
                raise ValueError('Listing unavailable for this owner')
            if not latest or latest['job_id'] != job_id:
                db.update_listing_analysis_job(job_id=job_id, owner_subject=owner_subject, status='superseded',
                    stage='superseded', completed=True)
                return
            snapshot = _prepare_inputs(db, current, files, settings, job_id, {
                'category': category or current['category'], 'item_size': item_size or current.get('size'),
                'user_condition': user_condition or current['condition'], 'item_description': item_description,
                'debug': debug, 'brand_override': brand_override, 'force_fresh_analysis': force_fresh_analysis,
                'stage_images_after_analysis': stage_images_after_analysis,
            })
        originals = _load_originals(db, snapshot, settings)
    except Exception as exc:
        # Input preparation is the only shared prerequisite. Fail visibly rather
        # than leaving a draft stuck in Analyzing when its originals are unreadable.
        current = db.get_listing_by_id(listing_id)
        latest = db.get_latest_listing_analysis_job(listing_id, owner_subject)
        if current and latest and latest['job_id'] == job_id:
            from .pipeline_results import mark_pricing_failure
            mark_pricing_failure(db, {
                'job_id': job_id, 'listing_id': listing_id, 'owner_subject': owner_subject,
                'photo_signature': photo_signature(current),
            })
            db.update_listing_analysis_job(job_id=job_id, owner_subject=owner_subject,
                status='failed', stage='input_failed', error=str(exc) or type(exc).__name__, completed=True)
            for state in db.list_pipeline_components(job_id):
                if state['status'] not in TERMINAL:
                    db.set_pipeline_component(job_id, state['component'], 'failed', state['attempts'], str(exc))
        if isinstance(exc, ValueError):
            log_json('listing_pipeline_input_failed', listing_id=listing_id, job_id=job_id, error=str(exc))
            return
        raise
    finally:
        db.close()
    # Copy the parent job-guard context so the nested pricing runner does not
    # reacquire its own lock. Each component uses a separate DB connection.
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix='listing-component') as executor:
        futures = [executor.submit(copy_context().run, _run_component, component, snapshot, copy.deepcopy(originals),
                                  settings, valuation_service, gpt_item_profiler)
                   for component in ('pricing', 'mannequin', 'staging')]
        for future in futures:
            future.result()
