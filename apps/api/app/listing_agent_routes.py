"""HTTP adapter and guarded domain tools for the opt-in listing agent."""
import hashlib
import io
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .auth import AuthPrincipal, get_request_principal
from .db import Database, PersistedImage, utc_now_iso
from .deps import get_gpt_item_profiler, get_settings, get_storage, get_valuation_service
from .listing_agent import Agent, Store, Turn, digest, valid_size
from .schemas import ListingCreateRequest
from .settings import Settings

router = APIRouter(prefix='/v1/listing-agent', tags=['listing-agent'])


def enabled(settings: Settings = Depends(get_settings)):
    if not settings.listing_agent_enabled:
        raise HTTPException(404, 'Listing agent is not enabled')
    return settings


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=1, max_length=120)


class RemovePhoto(Start):
    expected_revision: int = Field(ge=0)
    image_id: str = Field(min_length=1, max_length=120)


class ReviewListing(Start):
    listing_id: str = Field(min_length=1, max_length=120)


def invalidate_photo_evidence(state):
    if state.get('edit_proposal'):
        state['staged_changes'] = state['edit_proposal']['changes']
    state.update(evidence=None, waivers=[], approved=None, pending=None)
    state.pop('publication_approval', None)
    state.pop('edit_proposal', None)
    if state.get('listing_id'):
        state['photo_dirty'] = True
    if not state.get('listing_id') and state.get('fact_provenance', {}).get('category') == 'photo_detection':
        state['facts'].pop('category', None)
        state['fact_provenance'].pop('category', None)


class Services:
    def __init__(self, db, settings, principal, tasks):
        self.db, self.settings, self.principal, self.tasks = db, settings, principal, tasks

    def listing(self, state):
        listing = self.db.get_listing_by_id(state['listing_id']) if state['listing_id'] else None
        if not listing or listing.get('owner_subject') != self.principal.subject:
            raise HTTPException(404, 'Listing not found')
        return listing

    def files(self, state):
        from .main import _image_file_from_listing_url
        result = []
        for index, photo in enumerate(state['photos']):
            file = _image_file_from_listing_url(db=self.db, settings=self.settings,
                url=photo['url'], index=index, source_item_id=photo['item_id'])
            if not file or hashlib.sha256(file['data']).hexdigest() != photo['content_hash']:
                raise HTTPException(409, 'Photo evidence changed or is unavailable; upload originals again')
            result.append(file)
        return result

    def validate_draft_inputs(self, state, listing):
        from .pipeline_results import photo_key, photo_signature
        expected = sorted(photo_key(p['url']) for p in state['photos'])
        if photo_signature(listing) != expected or any(
                listing.get(key) != state['facts'].get(key) for key in ('category', 'condition', 'size')):
            raise HTTPException(409, 'The draft changed outside this conversation; continue in My Closet')

    async def assess(self, state):
        from .main import classify_image_roles, IMAGE_ROLE_REQUIREMENTS
        files = self.files(state)
        uploads = [UploadFile(file=io.BytesIO(f['data']), filename=f.get('filename', 'photo.jpg'),
                              headers={'content-type': f.get('content_type', 'image/jpeg')}) for f in files]
        try:
            response = await classify_image_roles(images=uploads, category=state['facts'].get('category'),
                                                  settings=self.settings, principal=self.principal)
            result = response.model_dump()
            # A user category correction changes required roles, not just a hint.
            category = state['facts'].get('category') or result['category']
            seen = {r for p in result['images'] for r in [p['role'], *p.get('additional_roles', [])]}
            result['missing_required'] = [r for r in IMAGE_ROLE_REQUIREMENTS[category]['required'] if r not in seen]
            return result | {'status': 'checked', 'category': category}
        except HTTPException as exc:
            if exc.status_code not in {503, 504}:
                raise
            return {'status': 'timed_out' if exc.status_code == 504 else 'unavailable',
                    'missing_required': [], 'category': None, 'category_confidence': 0,
                    'note': 'Only coverage was skipped. Category must be selected and full item/pricing analysis must run.'}
        finally:
            for upload in uploads:
                await upload.close()

    async def create_draft(self, state):
        from .main import _create_listing_for_owner
        facts = state['facts']
        photos = state['photos']
        self.files(state)  # Verify the exact confirmed originals still exist.
        payload = ListingCreateRequest(title=facts.get('title') or 'New listing', category=facts['category'],
            brand=facts.get('brand') or 'unknown', condition=facts['condition'], size=facts['size'],
            description=facts.get('description') or '', estimated_value=0, status='Review',
            images=[p['url'] for p in photos], image=photos[0]['url'], source_item_id=photos[0]['item_id'])
        listing_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'jouft-agent-draft:' + state['session_id']))
        response = _create_listing_for_owner(payload, self.tasks, self.principal, self.db, self.settings,
            get_valuation_service(), get_gpt_item_profiler(), listing_id=listing_id)
        if response.status not in {'Review', 'Analyzing', 'AnalysisFailed'}:
            raise HTTPException(409, 'This listing is no longer a private draft')
        self.validate_draft_inputs(state, response.model_dump())
        return response.model_dump()

    async def find_analysis_job(self, state):
        job_id = 'analysis-job-' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'jouft-agent-job:' + state['session_id']))
        return self.db.get_listing_analysis_job(job_id, self.principal.subject)

    async def start_analysis(self, state):
        from .main import _enqueue_existing_listing_analysis
        listing = self.listing(state)
        if listing['status'] not in {'Review', 'Analyzing', 'AnalysisFailed'}:
            raise HTTPException(409, 'The listing is no longer a private draft')
        self.files(state)
        job_id = 'analysis-job-' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'jouft-agent-job:' + state['session_id']))
        job = self.db.get_listing_analysis_job(job_id, self.principal.subject)
        latest = self.db.get_latest_listing_analysis_job(listing['listing_id'], self.principal.subject)
        if latest and latest['job_id'] != job_id:
            raise HTTPException(409, 'The draft has another analysis; continue in My Closet')
        if not job or job['status'] == 'queued':
            self.validate_draft_inputs(state, listing)
        if not job:
            job = self.db.create_listing_analysis_job(job_id=job_id, listing_id=listing['listing_id'],
                                                      owner_subject=self.principal.subject)
        if job['status'] == 'queued':
            self.db.execute(f'UPDATE listings SET status=\'Analyzing\',updated_at={self.db.param} '
                f'WHERE listing_id={self.db.param} AND owner_subject={self.db.param} AND status IN (\'Review\',\'AnalysisFailed\')',
                (utc_now_iso(), listing['listing_id'], self.principal.subject))
            self.db.commit()
            dispatch_key = 'dispatch:' + job_id
            lease = self.db.fetchone(f'SELECT updated_at FROM listing_agent_tools WHERE session_id={self.db.param} '
                                    f'AND tool_key={self.db.param}', (state['session_id'], dispatch_key))
            self.db.commit()
            if lease and (datetime.now(timezone.utc) - datetime.fromisoformat(lease[0])).total_seconds() < 60:
                return job
            self.db.execute(f'INSERT INTO listing_agent_tools VALUES ({self.db.param},{self.db.param},'
                f'\'dispatch_analysis\',\'running\',NULL,{self.db.param}) ON CONFLICT (session_id,tool_key) '
                'DO UPDATE SET updated_at=excluded.updated_at', (state['session_id'], dispatch_key, utc_now_iso()))
            self.db.commit()
            # Re-enqueueing a queued deterministic job recovers a crash between
            # database commit and dispatch, after a 60s dispatch lease expires.
            # Existing worker locks deduplicate deliveries without model retries.
            _enqueue_existing_listing_analysis(background_tasks=self.tasks, settings=self.settings,
                valuation_service=get_valuation_service(), gpt_item_profiler=get_gpt_item_profiler(),
                listing_id=listing['listing_id'], owner_subject=self.principal.subject,
                category=listing['category'], item_size=listing['size'], user_condition=listing['condition'],
                item_description=listing['description'], debug=True, stage_images_after_analysis=True,
                brand_override=state['facts'].get('brand') or None,
                job_id=job_id)
            self.db.execute(f'UPDATE listing_agent_tools SET status=\'scheduled\',result_json={self.db.param},'
                f'updated_at={self.db.param} WHERE session_id={self.db.param} AND tool_key={self.db.param}',
                (json.dumps({'job_id': job_id}), utc_now_iso(), state['session_id'], dispatch_key))
            self.db.commit()
        return job

    async def analysis_status(self, state):
        listing = self.listing(state)
        job = self.db.get_listing_analysis_job(state['job_id'], self.principal.subject) if state.get('job_id') else None
        if not state.get('job_id') and state.get('review_existing'):
            job = dict(job_id=None, listing_id=listing['listing_id'], status='succeeded' if listing.get('analysis') else 'failed', stage='saved_analysis')
        if not job or job.get('listing_id') != listing['listing_id']:
            raise HTTPException(409, 'Analysis job does not match this draft')
        latest = self.db.get_latest_listing_analysis_job(listing['listing_id'], self.principal.subject)
        current = not latest or latest['job_id'] == state['job_id']
        if current and not state.get('review_existing') and job['status'] == 'queued' and listing['status'] in {'Review', 'Analyzing', 'AnalysisFailed'}:
            await self.start_analysis(state)
        public = {k: listing.get(k) for k in ('listing_id', 'title', 'brand', 'category', 'condition', 'size',
                    'description', 'estimated_value', 'status', 'image', 'images')}
        public['pricing_review'] = (listing.get('analysis') or {}).get('pricing_review')
        from .main import _display_image_urls_from_storage_images, _normalize_public_image_url
        public['images'] = _display_image_urls_from_storage_images(listing.get('images') or [])
        public['image'] = _normalize_public_image_url(listing.get('image'))
        public['conversation_current'] = current
        return ({k: job.get(k) for k in ('job_id', 'status', 'stage')}, public)

    async def publication_review(self, state):
        listing = self.listing(state)
        job = self.db.get_listing_analysis_job(state['job_id'], self.principal.subject) if state.get('job_id') else None
        if not job and state.get('review_existing') and not state.get('job_id') and listing.get('analysis'):
            job = {'status': 'succeeded'}
        latest = self.db.get_latest_listing_analysis_job(listing['listing_id'], self.principal.subject)
        reasons = []
        if state.get('photo_dirty') or state.get('edit_proposal'):
            reasons.append('Confirm or discard your proposed changes before publishing.')
        if not job or job['status'] != 'succeeded' or (latest and latest['job_id'] != state['job_id']):
            reasons.append('The current analysis must finish successfully before publishing.')
        if listing['status'] != 'Review':
            reasons.append('This listing is not a private draft ready for review.')
        if not valid_size(listing):
            reasons.append('Select a valid size in My Closet before publishing.')
        analysis = listing.get('analysis') or {}
        value = float(listing.get('estimated_value') or 0)
        if (analysis.get('pricing_review') or {}).get('status') == 'pending' or not math.isfinite(value) or value <= 0:
            reasons.append('This item needs pricing review before publishing. You do not need to set a value.')
        if not listing.get('images') and not listing.get('image'):
            reasons.append('Add listing photos in My Closet before publishing.')
        assets = [a for a in analysis.get('generated_assets', []) if isinstance(a, dict) and a.get('synthetic')]
        return dict(token=digest({'listing': listing, 'job_id': state['job_id']}), publishable=not reasons,
                    reasons=reasons, mannequin_assets=assets, mannequin_choice_required=bool(assets))

    async def prepare_changes(self, state, changes):
        listing = self.listing(state)
        if listing['status'] != 'Review':
            raise HTTPException(409, 'Only private drafts can be corrected in this chat')
        proposed = {**listing, **changes}
        if not valid_size(proposed):
            raise HTTPException(400, 'Choose a valid size for the selected category')
        if any(not str(proposed.get(k) or '').strip() for k in ('title', 'brand', 'condition', 'category')):
            raise HTTPException(400, 'Title, brand, category and condition are required')
        if not state['photos']:
            raise HTTPException(400, 'Keep at least one photo before confirming changes')
        reanalyze = bool(state.get('photo_dirty') or any(proposed.get(k) != listing.get(k)
                         for k in ('brand', 'category', 'condition', 'size')))
        base = (await self.publication_review(state))['token']
        return dict(base=base, changes=changes, reanalyze=reanalyze,
                    token=digest([base, changes, [p['content_hash'] for p in state['photos']]]))

    async def apply_changes(self, state, proposal):
        from .main import update_listing
        listing = self.listing(state)
        if (await self.publication_review(state))['token'] != proposal['base']:
            raise HTTPException(409, 'The listing changed. Review and propose the changes again.')
        if listing['status'] != 'Review':
            raise HTTPException(409, 'The listing is no longer a private draft')
        values = {**listing, **proposal['changes'], 'status': 'Analyzing' if proposal['reanalyze'] else 'Review'}
        if state.get('photo_dirty'):
            self.files(state)
            values.update(images=[p['url'] for p in state['photos']], image=state['photos'][0]['url'], listed_images=[])
        result = update_listing(listing['listing_id'], ListingCreateRequest.model_validate(values), self.tasks,
            self.principal, self.db, self.settings, get_valuation_service(), get_gpt_item_profiler(),
            expected_updated_at=listing['updated_at'], expected_analysis_job_id=state.get('job_id'))
        latest = self.db.get_latest_listing_analysis_job(listing['listing_id'], self.principal.subject)
        state['job_id'] = latest['job_id'] if latest else None
        state['review_existing'] = True
        state['photo_dirty'] = False
        state['facts'] = {k: getattr(result, k) for k in ('title', 'brand', 'category', 'condition', 'size', 'description')}
        state['stage'] = 'analyzing' if result.status == 'Analyzing' else 'review_ready'
        return result.model_dump()

    async def publish(self, state, token, mannequin_choice):
        from .main import update_listing
        review = await self.publication_review(state)
        if review['token'] != token:
            raise HTTPException(409, 'The listing changed. Review the latest details before publishing.')
        if not review['publishable']:
            raise HTTPException(409, ' '.join(review['reasons']))
        if review['mannequin_choice_required'] and mannequin_choice not in {'include', 'exclude'}:
            raise HTTPException(409, 'Choose whether to include the mannequin image before publishing.')
        listing = self.listing(state)
        if digest({'listing': listing, 'job_id': state['job_id']}) != token:
            raise HTTPException(409, 'The listing changed. Review the latest details before publishing.')
        payload = ListingCreateRequest.model_validate({**listing, 'status': 'Active', 'mannequin_choice': mannequin_choice})
        # Reuse normal owner/subscription/manual-review/media/publication checks and notification.
        response = update_listing(listing['listing_id'], payload, self.tasks, self.principal,
                                  self.db, self.settings, get_valuation_service(), get_gpt_item_profiler(),
                                  expected_updated_at=listing['updated_at'], expected_analysis_job_id=state['job_id'])
        if response.status != 'Active':
            raise HTTPException(409, 'The listing was not published; review its current status in My Closet.')
        return response.model_dump()


def agent_for(settings, principal, tasks):
    # Dedicated DB connection: an async turn must not share session advisory locks
    # or transactions with another request using the cached legacy connection.
    db = Database(settings.database_url)
    return db, Agent(Store(db, principal.subject), settings, Services(db, settings, principal, tasks))


@router.get('/config')
def config(settings: Settings = Depends(get_settings), principal: AuthPrincipal = Depends(get_request_principal)):
    return {'enabled': settings.listing_agent_enabled}


@router.post('/sessions')
async def start(payload: Start, tasks: BackgroundTasks, settings: Settings = Depends(enabled),
                principal: AuthPrincipal = Depends(get_request_principal)):
    db, agent = agent_for(settings, principal, tasks)
    try:
        state = agent.store.create(payload.request_id)
        with agent.store.lock(state['session_id']):
            return await agent.public(agent.store.load(state['session_id']))
    finally:
        db.close()


@router.post('/sessions/review')
async def open_review(payload: ReviewListing, tasks: BackgroundTasks, settings: Settings = Depends(enabled),
                      principal: AuthPrincipal = Depends(get_request_principal)):
    from .main import _normalize_public_image_url, _image_file_from_listing_url
    db, agent = agent_for(settings, principal, tasks)
    try:
        listing = db.get_listing_by_id(payload.listing_id)
        if not listing or listing.get('owner_subject') != principal.subject:
            raise HTTPException(404, 'Listing not found')
        if listing['status'] not in {'Review', 'Analyzing', 'AnalysisFailed'}:
            raise HTTPException(409, 'This listing is not a private draft')
        state = agent.store.create('review:' + payload.listing_id)
        with agent.store.lock(state['session_id']):
            state = agent.store.load(state['session_id'])
            latest = db.get_latest_listing_analysis_job(listing['listing_id'], principal.subject)
            latest_id = latest['job_id'] if latest else None
            if not state.get('listing_id') or state.get('job_id') != latest_id or state['stage'] == 'closed':
                if state.get('photo_dirty') and not (state.get('edit_approval') and state['edit_approval'] == (state.get('edit_proposal') or {}).get('token')):
                    raise HTTPException(409, 'Finish or discard the proposed photo changes before reopening review')
                analysis = listing.get('analysis') or {}
                urls = list(dict.fromkeys(filter(None, [_normalize_public_image_url(
                    (entry.get('p_img') or entry.get('d_img')) if isinstance(entry, dict) else entry)
                    for entry in listing.get('images') or [listing.get('image')]])))
                generated = {_normalize_public_image_url(a.get('image_url')) for a in analysis.get('generated_assets', []) if isinstance(a, dict) and a.get('synthetic')}
                photos = []
                for index, url in enumerate(urls):
                    if url in generated:
                        continue
                    file = _image_file_from_listing_url(db=db, settings=settings, url=url, index=index, source_item_id=listing.get('source_item_id'))
                    if not file:
                        raise HTTPException(400, 'A saved photo could not be read. Please review the photos in My Closet.')
                    photos.append(dict(image_id=str(uuid.uuid5(uuid.NAMESPACE_URL, state['session_id'] + url)),
                        item_id=listing.get('source_item_id') or 'agent-' + state['session_id'], url=url,
                        content_hash=hashlib.sha256(file['data']).hexdigest()))
                state.update(listing_id=listing['listing_id'], job_id=latest_id, review_existing=True, photos=photos, saved_photos=photos[:],
                    facts={k: listing.get(k) for k in ('title', 'brand', 'category', 'condition', 'size', 'description')},
                    pending=None, approved=None, photo_dirty=False, evidence=None, waivers=[], stage='review_ready')
                state.pop('publication_approval', None)
                state.pop('edit_proposal', None)
                state.pop('staged_changes', None)
                agent.store.save(state)
            return await agent.public(state)
    finally:
        db.close()


@router.get('/sessions/active')
async def active(tasks: BackgroundTasks, settings: Settings = Depends(enabled),
                 principal: AuthPrincipal = Depends(get_request_principal)):
    db, agent = agent_for(settings, principal, tasks)
    try:
        row = db.fetchone(f'SELECT session_id FROM listing_agent_sessions WHERE owner_subject={db.param} '
                         'ORDER BY updated_at DESC LIMIT 1', (principal.subject,))
        db.commit()
        if not row:
            return {'session': None}
        with agent.store.lock(row[0]):
            return {'session': await agent.public(agent.store.load(row[0]))}
    finally:
        db.close()


@router.get('/sessions/{session_id}')
async def get_session(session_id: str, tasks: BackgroundTasks, settings: Settings = Depends(enabled),
                      principal: AuthPrincipal = Depends(get_request_principal)):
    db, agent = agent_for(settings, principal, tasks)
    try:
        with agent.store.lock(session_id):
            return await agent.public(agent.store.load(session_id))
    finally:
        db.close()


@router.post('/sessions/{session_id}/turns')
async def turn(session_id: str, payload: Turn, tasks: BackgroundTasks, settings: Settings = Depends(enabled),
               principal: AuthPrincipal = Depends(get_request_principal)):
    if not settings.openai_api_key:
        raise HTTPException(503, 'Listing agent is temporarily unavailable')
    db, agent = agent_for(settings, principal, tasks)
    try:
        return await agent.turn(session_id, payload)
    finally:
        db.close()


@router.post('/sessions/{session_id}/photos')
async def photos(session_id: str, tasks: BackgroundTasks,
                 images: Annotated[list[UploadFile], File()], request_id: Annotated[str, Form(min_length=1, max_length=120)],
                 expected_revision: Annotated[int, Form(ge=0)], settings: Settings = Depends(enabled),
                 principal: AuthPrincipal = Depends(get_request_principal)):
    if not 1 <= len(images) <= 6:
        raise HTTPException(400, 'Upload 1–6 photos')
    db, agent = agent_for(settings, principal, tasks)
    try:
        with agent.store.lock(session_id):
            state = agent.store.load(session_id)
            if state['listing_id'] and state['stage'] != 'review_ready':
                raise HTTPException(409, 'Use the listing editor to change an existing draft')
            files = []
            for image in images:
                data = await image.read(15 * 1024 * 1024 + 1)
                if not data or len(data) > 15 * 1024 * 1024:
                    raise HTTPException(400, 'Each photo must be between 1 byte and 15 MB')
                try:
                    with Image.open(io.BytesIO(data)) as opened:
                        fmt = opened.format
                        if opened.width * opened.height > 40_000_000:
                            raise ValueError('Photo is too large')
                        opened.verify()
                    if fmt not in {'JPEG', 'PNG', 'WEBP'}:
                        raise ValueError('Unsupported format')
                except Exception as exc:
                    raise HTTPException(400, 'Upload readable JPEG, PNG or WebP photos') from exc
                files.append((data, fmt, hashlib.sha256(data).hexdigest()))
            operation = Turn(request_id=request_id, expected_revision=expected_revision,
                             message='Add photos: ' + ','.join(f[2] for f in files))
            previous, resumed = agent.store.request(state, operation)
            if previous is not None:
                return previous
            hashes = {p['content_hash'] for p in state['photos']} | {f[2] for f in files}
            if len(hashes) > 6:
                raise HTTPException(400, 'A draft can have up to 6 photos. Remove a saved photo before adding more.')
            item_id = 'agent-' + session_id
            db.insert_item(item_id)
            stored = list(state['photos'])
            storage = get_storage()
            for data, fmt, content_hash in files:
                if any(p['content_hash'] == content_hash for p in stored):
                    continue
                image_id = str(uuid.uuid5(uuid.NAMESPACE_URL, session_id + ':' + content_hash))
                mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}[fmt]
                filename = image_id + {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[fmt]
                if not db.get_image_storage_uri(image_id):
                    uri = storage.save_upload(item_id, filename, mime, data)
                    db.insert_image(PersistedImage(image_id=image_id, item_id=item_id, storage_uri=uri,
                        filename=filename, role_hint='full_item' if not stored else 'close_up', content_hash=content_hash))
                if not any(p['image_id'] == image_id for p in stored):
                    stored.append(dict(image_id=image_id, item_id=item_id, url='/v1/images/' + image_id, content_hash=content_hash))
            if stored != state['photos']:
                if state.get('listing_id') and not state.get('photo_dirty'):
                    state['saved_photos'] = state['photos'][:]
                state['photos'] = stored
                invalidate_photo_evidence(state)
            agent.store.save(state)
            result = await agent.public(state)
            agent.store.complete(state, operation, result)
            return result
    finally:
        db.close()


@router.post('/sessions/{session_id}/photos/remove')
async def remove_photo(session_id: str, payload: RemovePhoto, tasks: BackgroundTasks,
                       settings: Settings = Depends(enabled),
                       principal: AuthPrincipal = Depends(get_request_principal)):
    db, agent = agent_for(settings, principal, tasks)
    try:
        with agent.store.lock(session_id):
            state = agent.store.load(session_id)
            if state['listing_id'] and state['stage'] != 'review_ready':
                raise HTTPException(409, 'Use the listing editor to change an existing draft')
            operation = Turn(request_id=payload.request_id, expected_revision=payload.expected_revision,
                             message='Remove photo: ' + payload.image_id)
            previous, resumed = agent.store.request(state, operation)
            if previous is not None:
                return previous
            remaining = [p for p in state['photos'] if p['image_id'] != payload.image_id]
            if len(remaining) == len(state['photos']) and not (resumed and
                    state.get('last_photo_removal') == [payload.request_id, payload.image_id]):
                raise HTTPException(404, 'Photo is not in this conversation')
            if remaining != state['photos']:
                if state.get('listing_id') and not state.get('photo_dirty'):
                    state['saved_photos'] = state['photos'][:]
                state['photos'] = remaining
                state['last_photo_removal'] = [payload.request_id, payload.image_id]
                invalidate_photo_evidence(state)
            agent.store.save(state)
            result = await agent.public(state)
            agent.store.complete(state, operation, result)
            return result
    finally:
        db.close()
