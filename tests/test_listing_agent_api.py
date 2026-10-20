import io

import pytest
from PIL import Image

from test_api_integration import _build_client
from test_listing_agent import scripted


AUTH = {'x-api-key': 'test-key'}


def photo(color='red'):
    data = io.BytesIO()
    Image.new('RGB', (32, 32), color).save(data, format='JPEG')
    return data.getvalue()


@pytest.fixture
def client(monkeypatch):
    client = _build_client()
    from app.deps import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'listing_agent_enabled', True)
    monkeypatch.setattr(settings, 'openai_api_key', 'test-never-sent')
    return client


def start(client):
    response = client.post('/v1/listing-agent/sessions', headers=AUTH, json={'request_id': 'one'})
    assert response.status_code == 200, response.text
    return response.json()


def review_ready(client, analysis=None):
    from app.deps import get_db
    from app.listing_agent import Store
    state = upload(client, start(client)).json()
    url = state['photos'][0]['url']
    response = client.post('/v1/listings', headers=AUTH, json=dict(title='Reviewed coat', brand='Chanel',
        category='clothes', condition='New', size='M', estimated_value=123, status='Review',
        image=url, images=[url], source_item_id=state['photos'][0]['item_id'], analysis=analysis))
    assert response.status_code == 200, response.text
    db = get_db()
    job = db.create_listing_analysis_job(job_id='review-job', listing_id=response.json()['listing_id'], owner_subject='api-key')
    db.update_listing_analysis_job(job_id=job['job_id'], owner_subject='api-key', status='succeeded', stage='completed', completed=True)
    store = Store(db, 'api-key')
    saved = store.load(state['session_id'])
    saved.update(listing_id=response.json()['listing_id'], job_id=job['job_id'], stage='analyzing')
    store.save(saved)
    result = client.get(f'/v1/listing-agent/sessions/{state["session_id"]}', headers=AUTH)
    assert result.status_code == 200, result.text
    return result.json()


def test_general_review_handoff_resolves_first_result_and_opens_owned_session(client, monkeypatch):
    import json
    from app import main
    state = review_ready(client)
    class Response:
        status_code = 200
        def json(self):
            return {'output': [{'content': [{'type': 'output_text', 'text': json.dumps(dict(
                intent='review_listing', reply='Review it', listing_reference=None, listing_reference_index=1,
                listing_reference_scope='closet', navigation=None))}]}]}
    class Model:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): return Response()
    monkeypatch.setattr(main.httpx, 'AsyncClient', Model)
    result = client.post('/v1/app-assistant/chat', headers=AUTH, json=dict(
        messages=[{'role': 'user', 'content': 'review first one'}], context={
            'closet_result_ids': [state['listing_id']], 'result_listing_ids': [state['listing_id']]}))
    assert result.status_code == 200, result.text
    assert result.json()['review_listing_id'] == state['listing_id']
    opened = client.post('/v1/listing-agent/sessions/review', headers=AUTH,
                         json=dict(request_id='review-entry', listing_id=state['listing_id']))
    assert opened.status_code == 200, opened.text
    assert opened.json()['listing']['title'] == 'Reviewed coat'
    assert opened.json()['stage'] == 'review_ready'


def test_review_corrections_are_proposed_confirmed_and_invalidate_publication(client):
    from app.deps import get_db
    state = review_ready(client)
    old_token = state['publication_review']['token']
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    response = client.post(path, headers=AUTH, json=dict(request_id='propose-title', expected_revision=state['revision'],
        message='Correct the title', edit_fields={'title': 'Corrected coat'}))
    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal['pending']['type'] == 'confirm_changes'
    assert not proposal['pending']['reanalyze']
    assert not proposal['publication_review']['publishable']
    assert get_db().get_listing_by_id(state['listing_id'])['title'] == 'Reviewed coat'
    payload = dict(request_id='save-title', expected_revision=proposal['revision'], message='Confirm changes', edit_token=proposal['pending']['token'])
    response = client.post(path, headers=AUTH, json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['listing']['title'] == 'Corrected coat' and saved['listing']['status'] == 'Review'
    assert saved['listing']['estimated_value'] == 123
    assert saved['pending'] is None
    assert client.post(path, headers=AUTH, json=payload).json() == saved
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1
    assert client.post(path, headers=AUTH, json=dict(request_id='old-publish', expected_revision=saved['revision'],
        message='Publish', publication_token=old_token)).status_code == 409


def test_followup_question_does_not_add_another_confirmation_for_saved_proposal(client, monkeypatch):
    from app import listing_agent
    state = review_ready(client)
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    proposed = client.post(path, headers=AUTH, json=dict(request_id='propose-followup',
        expected_revision=state['revision'], message='Change title',
        edit_fields={'title': 'Corrected coat'})).json()
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('ask_user',
        {'field': 'details', 'question': 'Do you want me to proceed once you confirm?'})))
    response = client.post(path, headers=AUTH, json=dict(request_id='followup-confirm',
        expected_revision=proposed['revision'], message='confirm'))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['edit_proposal']['token'] == proposed['edit_proposal']['token']
    assert 'Choose Save changes' in result['messages'][-1]['content']
    assert 'Do you want me' not in result['messages'][-1]['content']
    assert not result['publication_review']['publishable']
    assert result['listing']['title'] == 'Reviewed coat'


def test_natural_correction_uses_proposal_tool_and_analysis_sensitive_edits_reanalyze(client, monkeypatch):
    from app import listing_agent, main
    from app.deps import get_db
    state = review_ready(client)
    queued = []
    monkeypatch.setattr(main, '_enqueue_existing_listing_analysis', lambda **kwargs: queued.append(kwargs))
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('propose_listing_changes',
        {'facts': {'condition': 'NewWithTags'}, 'evidence_quote': 'Change condition to NewWithTags'})))
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    response = client.post(path, headers=AUTH, json=dict(request_id='natural-edit', expected_revision=state['revision'],
        message='Change condition to NewWithTags'))
    assert response.status_code == 200, response.text
    assert response.json()['stage'] == 'analyzing'
    assert response.json()['listing']['condition'] == 'NewWithTags'
    assert len(queued) == 1
    assert client.post(path, headers=AUTH, json=dict(request_id='natural-edit', expected_revision=state['revision'],
        message='Change condition to NewWithTags')).json() == response.json()
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 2


def test_chat_size_correction_saves_without_confirmation_and_preserves_value(client, monkeypatch):
    from app import listing_agent
    from app.deps import get_db
    state = review_ready(client)
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('propose_listing_changes',
        {'facts': {'size': 'L'}, 'evidence_quote': 'Change size to L'})))
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    payload = dict(request_id='size-direct', expected_revision=state['revision'], message='Change size to L')
    response = client.post(path, headers=AUTH, json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['listing']['size'] == 'L'
    assert result['listing']['estimated_value'] == 123
    assert result['edit_proposal'] is None and result['stage'] == 'review_ready'
    assert 'Changes saved' in result['messages'][-1]['content']
    assert result['listing']['status'] == 'Review'
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1
    assert client.post(path, headers=AUTH, json=payload).json() == result


def test_hypothetical_correction_is_not_saved(client, monkeypatch):
    from app import listing_agent
    state = review_ready(client)
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('propose_listing_changes',
        {'facts': {'size': 'L'}, 'evidence_quote': 'Should I change size to L?'})))
    response = client.post(f'/v1/listing-agent/sessions/{state["session_id"]}/turns', headers=AUTH,
        json=dict(request_id='hypothetical-size', expected_revision=state['revision'], message='Should I change size to L?'))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['listing']['size'] == 'M'
    assert result['listing']['estimated_value'] == 123
    assert result['edit_proposal']['changes'] == {'size': 'L'}


def test_review_photo_changes_are_staged_and_can_be_discarded(client):
    from app.deps import get_db
    state = review_ready(client)
    original_images = get_db().get_listing_by_id(state['listing_id'])['images']
    staged = upload(client, state, photo('blue'), 'extra').json()
    assert staged['photo_dirty'] and len(staged['photos']) == 2
    assert not staged['publication_review']['publishable']
    assert get_db().get_listing_by_id(state['listing_id'])['images'] == original_images
    response = client.post(f'/v1/listing-agent/sessions/{state["session_id"]}/turns', headers=AUTH,
        json=dict(request_id='discard', expected_revision=staged['revision'], message='Discard changes'))
    assert response.status_code == 200, response.text
    assert len(response.json()['photos']) == 1 and not response.json()['photo_dirty']
    assert get_db().get_listing_by_id(state['listing_id'])['images'] == original_images


def test_photo_changes_confirm_once_and_rerun_analysis(client, monkeypatch):
    from app import main
    from app.deps import get_db
    state = review_ready(client)
    queued = []
    monkeypatch.setattr(main, '_enqueue_existing_listing_analysis', lambda **kwargs: queued.append(kwargs))
    staged = upload(client, state, photo('blue'), 'new-photo').json()
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    result = client.post(path, headers=AUTH, json=dict(request_id='propose-photos', expected_revision=staged['revision'], message='I added a photo'))
    assert result.status_code == 200, result.text
    proposal = result.json()
    assert proposal['pending']['reanalyze'] and proposal['pending']['photo_count'] == 2
    payload = dict(request_id='confirm-photos', expected_revision=proposal['revision'], message='Confirm changes', edit_token=proposal['pending']['token'])
    result = client.post(path, headers=AUTH, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['stage'] == 'analyzing' and len(queued) == 1
    assert len(get_db().get_listing_by_id(state['listing_id'])['images']) == 2
    assert client.post(path, headers=AUTH, json=payload).json() == result.json()
    assert len(queued) == 1


def test_review_edits_cannot_set_value_or_skip_confirmation(client, monkeypatch):
    from app import listing_agent
    from app.deps import get_db
    state = review_ready(client)
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    assert client.post(path, headers=AUTH, json=dict(request_id='price', expected_revision=state['revision'],
        message='Set value', edit_fields={'estimated_value': 9999})).status_code == 422
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('apply_listing_changes', {}), ('prepare_draft_review', {})))
    result = client.post(path, headers=AUTH, json=dict(request_id='prose-save', expected_revision=state['revision'], message='yes save and publish'))
    assert result.status_code == 200
    assert get_db().get_listing_by_id(state['listing_id'])['estimated_value'] == 123
    assert get_db().get_listing_by_id(state['listing_id'])['status'] == 'Review'


def test_photo_staging_preserves_prior_text_proposal(client):
    state = review_ready(client)
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    proposed = client.post(path, headers=AUTH, json=dict(request_id='text-before-photo', expected_revision=state['revision'],
        message='Correct title', edit_fields={'title': 'Corrected coat'})).json()
    staged = upload(client, proposed, photo('blue'), 'photo-after-text').json()
    result = client.post(path, headers=AUTH, json=dict(request_id='merge', expected_revision=staged['revision'], message='I added a photo'))
    assert result.status_code == 200, result.text
    assert result.json()['pending']['changes']['title'] == 'Corrected coat'
    assert result.json()['pending']['photo_count'] == 2
    assert result.json()['pending']['reanalyze']


def test_stale_edit_proposal_cannot_overwrite_external_correction(client):
    from app.deps import get_db
    state = review_ready(client)
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    proposal = client.post(path, headers=AUTH, json=dict(request_id='edit-base', expected_revision=state['revision'],
        message='Correct title', edit_fields={'title': 'Requested title'})).json()
    db = get_db()
    db.execute('UPDATE listings SET title=? WHERE listing_id=?', ('External title', state['listing_id']))
    db.commit()
    response = client.post(path, headers=AUTH, json=dict(request_id='stale-edit', expected_revision=proposal['revision'],
        message='Confirm changes', edit_token=proposal['pending']['token']))
    assert response.status_code == 409
    assert db.get_listing_by_id(state['listing_id'])['title'] == 'External title'


def test_review_entry_is_owner_scoped_and_never_creates_another_listing(client):
    from app.auth import AuthPrincipal, get_request_principal
    from app import main
    from app.deps import get_db
    state = review_ready(client)
    payload = dict(request_id='entry', listing_id=state['listing_id'])
    main.app.dependency_overrides[get_request_principal] = lambda: AuthPrincipal(auth_type='clerk', subject='other', claims={})
    try:
        assert client.post('/v1/listing-agent/sessions/review', headers=AUTH, json=payload).status_code == 404
    finally:
        main.app.dependency_overrides.pop(get_request_principal, None)
    first = client.post('/v1/listing-agent/sessions/review', headers=AUTH, json=payload)
    second = client.post('/v1/listing-agent/sessions/review', headers=AUTH, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()['session_id'] == second.json()['session_id']
    assert len(get_db().list_owner_listings('api-key')) == 1
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1


def test_review_publish_requires_its_own_approval_and_is_idempotent(client, monkeypatch):
    from app.deps import get_db
    from app import listing_agent
    async def no_model(*args):
        pytest.fail('Review/publication control must not need a model call')
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('prepare_draft_review', {})))
    state = review_ready(client)
    assert state['stage'] == 'review_ready' and state['publication_review']['publishable']
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    prose = client.post(path, headers=AUTH, json=dict(request_id='prose', expected_revision=state['revision'], message='yes publish it'))
    assert prose.status_code == 200, prose.text
    assert get_db().get_listing_by_id(state['listing_id'])['status'] == 'Review'
    state = prose.json()
    payload = dict(request_id='publish', expected_revision=state['revision'], message='Confirm and publish',
                   publication_token=state['publication_review']['token'])
    response = client.post(path, headers=AUTH, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['stage'] == 'published'
    assert response.json()['listing']['status'] == 'Active'
    assert client.post(path, headers=AUTH, json=payload).json() == response.json()
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1


def test_publication_rejects_stale_review_and_manual_pricing_review(client):
    from app.deps import get_db
    state = review_ready(client)
    path = f'/v1/listing-agent/sessions/{state["session_id"]}'
    db = get_db()
    db.execute('UPDATE listings SET title=? WHERE listing_id=?', ('Changed title', state['listing_id']))
    db.commit()
    response = client.post(path + '/turns', headers=AUTH, json=dict(request_id='stale-publish',
        expected_revision=state['revision'], message='Publish', publication_token=state['publication_review']['token']))
    assert response.status_code == 409
    assert db.get_listing_by_id(state['listing_id'])['status'] == 'Review'
    db.execute('UPDATE listings SET analysis_json=? WHERE listing_id=?',
               ('{"pricing_review":{"status":"pending"}}', state['listing_id']))
    db.commit()
    current = client.get(path, headers=AUTH).json()
    assert not current['publication_review']['publishable']
    assert client.post(path + '/turns', headers=AUTH, json=dict(request_id='manual-review',
        expected_revision=current['revision'], message='Publish', publication_token=current['publication_review']['token'])).status_code == 409


@pytest.mark.parametrize('choice', ['include', 'exclude'])
def test_publication_requires_explicit_mannequin_choice(client, choice):
    import json
    from app.deps import get_db
    state = review_ready(client)
    url = client.post('/v1/uploads/images', headers=AUTH, data={'item_id': 'generated-preview'},
        files=[('images', ('preview.jpg', photo('blue'), 'image/jpeg'))]).json()['uploaded_images'][0]['image_url']
    db = get_db()
    analysis = {'generated_assets': [dict(synthetic=True, kind='mannequin', image_url=url, review_decision='pending')]}
    db.execute('UPDATE listings SET analysis_json=? WHERE listing_id=?', (json.dumps(analysis), state['listing_id']))
    db.commit()
    path = f'/v1/listing-agent/sessions/{state["session_id"]}'
    state = client.get(path, headers=AUTH).json()
    assert state['publication_review']['mannequin_choice_required']
    payload = dict(request_id='publish-choice', expected_revision=state['revision'], message='Publish reviewed listing',
                   publication_token=state['publication_review']['token'])
    assert client.post(path + '/turns', headers=AUTH, json=payload).status_code == 409
    payload.update(request_id='publish-with-choice', mannequin_choice=choice)
    response = client.post(path + '/turns', headers=AUTH, json=payload)
    assert response.status_code == 200, response.text
    listing = db.get_listing_by_id(state['listing_id'])
    assert listing['status'] == 'Active'
    assert listing['analysis']['generated_assets'][0]['review_decision'] == choice
    assert client.post(path + '/turns', headers=AUTH, json=payload).json() == response.json()


@pytest.mark.parametrize('race', ['edit', 'analysis'])
def test_publication_blocks_concurrent_edit_at_database_write(client, monkeypatch, race):
    from app.db import Database
    from app.deps import get_db
    state = review_ready(client)
    original = Database.update_listing
    def racing_update(self, **kwargs):
        if kwargs.get('expected_updated_at'):
            if race == 'edit':
                self.execute('UPDATE listings SET title=?,updated_at=? WHERE listing_id=?',
                             ('Concurrent correction', '2099-01-01T00:00:00+00:00', state['listing_id']))
                self.commit()
            else:
                self.create_listing_analysis_job(job_id='new-analysis', listing_id=state['listing_id'], owner_subject='api-key')
        return original(self, **kwargs)
    monkeypatch.setattr(Database, 'update_listing', racing_update)
    response = client.post(f'/v1/listing-agent/sessions/{state["session_id"]}/turns', headers=AUTH,
        json=dict(request_id='race', expected_revision=state['revision'], message='Publish',
                  publication_token=state['publication_review']['token']))
    assert response.status_code == 409
    listing = get_db().get_listing_by_id(state['listing_id'])
    assert listing['status'] == 'Review'
    assert listing['title'] == ('Concurrent correction' if race == 'edit' else 'Reviewed coat')


def test_publication_recovers_after_write_before_tool_checkpoint(client, monkeypatch):
    from app import listing_agent_routes
    state = review_ready(client)
    original = listing_agent_routes.Services.publish
    async def interrupted(self, *args):
        await original(self, *args)
        raise RuntimeError('Lost response after publication')
    monkeypatch.setattr(listing_agent_routes.Services, 'publish', interrupted)
    payload = dict(request_id='resume-publish', expected_revision=state['revision'], message='Publish',
                   publication_token=state['publication_review']['token'])
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    assert client.post(path, headers=AUTH, json=payload).status_code == 409
    response = client.post(path, headers=AUTH, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['stage'] == 'published'


def test_publication_keeps_subscription_and_owner_checks(client, monkeypatch):
    from app.auth import AuthPrincipal, get_request_principal
    from app import main
    from app.deps import get_db
    from fastapi import HTTPException
    state = review_ready(client)
    payload = dict(request_id='protected-publish', expected_revision=state['revision'], message='Publish',
                   publication_token=state['publication_review']['token'])
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    main.app.dependency_overrides[get_request_principal] = lambda: AuthPrincipal(auth_type='clerk', subject='other', claims={})
    try:
        assert client.post(path, headers=AUTH, json=payload).status_code == 404
    finally:
        main.app.dependency_overrides.pop(get_request_principal, None)
    def subscription_required(*args):
        raise HTTPException(402, 'Subscription required')
    monkeypatch.setattr(main, '_require_subscription_entitlement', subscription_required)
    response = client.post(path, headers=AUTH, json=payload)
    assert response.status_code == 409 and 'Subscription required' in response.text
    assert get_db().get_listing_by_id(state['listing_id'])['status'] == 'Review'


def upload(client, state, data=None, request='photos'):
    return client.post(f'/v1/listing-agent/sessions/{state["session_id"]}/photos', headers=AUTH,
        data={'request_id': request, 'expected_revision': state['revision']},
        files=[('images', ('photo.jpg', data or photo(), 'image/jpeg'))])


def test_disabled_route_and_auth_required(client, monkeypatch):
    from app.deps import get_settings
    assert client.post('/v1/listing-agent/sessions', json={'request_id': 'x'}).status_code == 401
    monkeypatch.setattr(get_settings(), 'listing_agent_enabled', False)
    assert client.post('/v1/listing-agent/sessions', headers=AUTH, json={'request_id': 'x'}).status_code == 404


def test_additive_photos_deduplicate_enforce_limit_and_remove_safely(client):
    state = upload(client, start(client)).json()
    first = state['photos'][0]
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/photos'
    for i, color in enumerate(['blue', 'green', 'yellow', 'black', 'white']):
        response = upload(client, state, photo(color), f'add-{i}')
        assert response.status_code == 200, response.text
        state = response.json()
    assert len(state['photos']) == 6 and state['photos'][0] == first
    assert upload(client, state, photo('purple'), 'overflow').status_code == 400
    # Duplicate content at capacity is harmless, and replay does not append again.
    duplicate = upload(client, state, photo(), 'duplicate')
    assert duplicate.status_code == 200, duplicate.text
    assert len(duplicate.json()['photos']) == 6
    assert upload(client, state, photo(), 'duplicate').json() == duplicate.json()
    state = duplicate.json()
    payload = dict(request_id='remove', expected_revision=state['revision'], image_id=first['image_id'])
    removed = client.post(path + '/remove', headers=AUTH, json=payload)
    assert removed.status_code == 200, removed.text
    assert len(removed.json()['photos']) == 5
    assert first not in removed.json()['photos']
    assert removed.json()['evidence'] is None and removed.json()['pending'] is None
    assert client.post(path + '/remove', headers=AUTH, json=payload).json() == removed.json()
    assert client.post(path + '/remove', headers=AUTH, json=dict(request_id='stale',
        expected_revision=state['revision'], image_id=state['photos'][1]['image_id'])).status_code == 409
    assert upload(client, removed.json(), photo('purple'), 'new-slot').status_code == 200


def test_remove_photo_is_owner_scoped_and_allows_removing_last_photo(client):
    from app.auth import AuthPrincipal, get_request_principal
    from app.main import app
    state = upload(client, start(client)).json()
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/photos/remove'
    payload = dict(request_id='remove-last', expected_revision=state['revision'], image_id=state['photos'][0]['image_id'])
    app.dependency_overrides[get_request_principal] = lambda: AuthPrincipal(auth_type='clerk', subject='other', claims={})
    try:
        assert client.post(path, headers=AUTH, json=payload).status_code == 404
    finally:
        app.dependency_overrides.pop(get_request_principal, None)
    missing = dict(payload, request_id='missing', image_id='not-in-this-session')
    assert client.post(path, headers=AUTH, json=missing).status_code == 404
    assert client.post(path, headers=AUTH, json=missing).status_code == 404
    result = client.post(path, headers=AUTH, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['photos'] == []
    assert not result.json()['analysis_confirmed']


def test_real_photo_upload_invalidates_missing_sole_and_rechecks_once(client, monkeypatch):
    from app import listing_agent, listing_agent_routes
    assessed = []
    async def assess(self, state):
        self.files(state)
        assessed.append(len(state['photos']))
        return dict(status='checked', category='shoes', category_confidence=1,
                    missing_required=['shoe_sole'] if len(state['photos']) == 1 else [],
                    missing_recommended=['condition_or_wear'])
    monkeypatch.setattr(listing_agent_routes.Services, 'assess', assess)
    state = upload(client, start(client)).json()
    path = f'/v1/listing-agent/sessions/{state["session_id"]}'
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('assess_photo_evidence', {}),
        ('ask_user', {'field': 'photos', 'question': 'Add the sole.'})))
    state = client.post(path + '/turns', headers=AUTH, json=dict(request_id='first',
        expected_revision=state['revision'], message='Check my photos')).json()
    assert 'shoe sole' in state['reply']
    uploaded = client.post(path + '/photos', headers=AUTH,
        data={'request_id': 'with-sole', 'expected_revision': state['revision']},
        files=[('images', ('front.jpg', photo(), 'image/jpeg')),
               ('images', ('sole.jpg', photo('blue'), 'image/jpeg'))]).json()
    assert len(uploaded['photos']) == 2
    assert uploaded['evidence'] is None and uploaded['pending'] is None
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('assess_photo_evidence', {}),
        ('record_user_facts', {'facts': {'condition': 'New', 'size': 'US 8'}, 'evidence_quote': 'New, size US 8'}),
        ('prepare_analysis_confirmation', {})))
    response = client.post(path + '/turns', headers=AUTH, json=dict(request_id='second',
        expected_revision=uploaded['revision'], message='New, size US 8'))
    assert response.status_code == 200, response.text
    assert response.json()['pending']['type'] == 'confirm_analysis'
    assert response.json()['evidence']['missing_required'] == []
    assert assessed == [1, 2]


def test_real_private_draft_and_job_are_idempotent_and_can_resume(client, monkeypatch):
    from app import listing_agent, listing_agent_routes, main
    from app.deps import get_db
    db = get_db()
    enqueued = []
    monkeypatch.setattr(main, '_enqueue_existing_listing_analysis', lambda **kwargs: enqueued.append(kwargs))
    async def assess(self, state):
        self.files(state)  # Exercise actual persisted upload resolution and hash verification.
        return dict(status='checked', category='clothes', category_confidence=.95, missing_required=[])
    monkeypatch.setattr(listing_agent_routes.Services, 'assess', assess)
    state = start(client)
    assert start(client)['session_id'] == state['session_id']
    response = upload(client, state)
    assert response.status_code == 200, response.text
    uploaded = response.json()
    assert uploaded['photos'][0]['content_hash']
    assert upload(client, state).json() == uploaded
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('assess_photo_evidence', {}),
        ('record_user_facts', {'facts': {'condition': 'New', 'size': 'M'}, 'evidence_quote': 'New, size M'}),
        ('prepare_analysis_confirmation', {})))
    path = f'/v1/listing-agent/sessions/{state["session_id"]}'
    response = client.post(path + '/turns', headers=AUTH, json=dict(request_id='details',
        expected_revision=uploaded['revision'], message='New, size M'))
    assert response.status_code == 200, response.text
    prepared = response.json()
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('create_private_draft', {}), ('start_listing_analysis', {})))
    confirmation = dict(request_id='confirm', expected_revision=prepared['revision'], message='Confirm private draft',
                        confirmation_token=prepared['pending']['token'])
    response = client.post(path + '/turns', headers=AUTH, json=confirmation)
    assert response.status_code == 200, response.text
    running = response.json()
    listing = db.get_listing_by_id(running['listing_id'])
    assert listing['owner_subject'] == 'api-key'
    assert listing['status'] == 'Analyzing'
    assert listing['condition'] == 'New'
    assert listing['images'][0] == uploaded['photos'][0]['url']
    assert len(enqueued) == 1  # Refreshes in this turn do not flood the queue.
    assert {e['job_id'] for e in enqueued} == {running['job_id']}
    assert client.post(path + '/turns', headers=AUTH, json=confirmation).json() == running
    assert len(db.list_owner_listings('api-key')) == 1
    assert len(db.fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1
    db.update_listing_analysis_job(job_id=running['job_id'], owner_subject='api-key', status='succeeded', stage='completed', completed=True)
    # A successful result is read from the real listing; no model needs to run.
    db.execute('UPDATE listings SET status=\'Review\',estimated_value=123 WHERE listing_id=?', (running['listing_id'],))
    db.commit()
    resumed = client.get('/v1/listing-agent/sessions/active', headers=AUTH).json()['session']
    assert resumed['stage'] == 'review_ready'
    assert resumed['listing']['estimated_value'] == 123
    assert resumed['listing']['status'] != 'Active'
    staged = upload(client, resumed, request='changed-after-draft')
    assert staged.status_code == 200
    assert client.post(path + '/photos/remove', headers=AUTH, json=dict(request_id='remove-after-draft',
        expected_revision=staged.json()['revision'], image_id=uploaded['photos'][0]['image_id'])).status_code == 200
    assert db.get_listing_by_id(running['listing_id'])['images']  # Staging does not edit saved listing.
    db.create_listing_analysis_job(job_id='external-edit-job', listing_id=running['listing_id'], owner_subject='api-key')
    handed_off = client.get(path, headers=AUTH).json()
    assert handed_off['stage'] == 'closed'
    assert handed_off['listing']['conversation_current'] is False


def test_crash_after_draft_insert_recovers_without_duplicate_creation(client, monkeypatch):
    from app import main, listing_agent
    from app.deps import get_db, get_settings
    from app.db import Database
    from app.listing_agent import Agent, Store
    state = upload(client, start(client)).json()
    db = Database(get_settings().database_url)
    try:
        store = Store(db, 'api-key')
        saved = store.load(state['session_id'])
        saved.update(facts=dict(category='clothes', condition='New', size='M'),
                     evidence=dict(status='checked', missing_required=[]))
        saved['approved'] = Agent.version(saved)
        store.save(saved)
        original = main._create_listing_for_owner
        crashed = []
        def create_then_crash(*args, **kwargs):
            result = original(*args, **kwargs)
            if not crashed:
                crashed.append(True)
                raise RuntimeError('Process interrupted after durable draft insert')
            return result
        monkeypatch.setattr(main, '_create_listing_for_owner', create_then_crash)
        monkeypatch.setattr(main, '_enqueue_existing_listing_analysis', lambda **kwargs: None)
        model = scripted(('create_private_draft', {}), ('create_private_draft', {}), ('start_listing_analysis', {}))
        monkeypatch.setattr(listing_agent, 'call_model', model)
        response = client.post(f'/v1/listing-agent/sessions/{saved["session_id"]}/turns', headers=AUTH,
            json=dict(request_id='recover', expected_revision=saved['revision'], message='Continue my confirmed draft.'))
        assert response.status_code == 200, response.text
        assert response.json()['stage'] == 'analyzing'
        assert len(get_db().list_owner_listings('api-key')) == 1
        assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1
        assert 'Tool could not finish' in model.captured[1][-1]['output']
    finally:
        db.close()


def test_queued_job_dispatch_is_leased_and_recovers_after_interruption(client, monkeypatch):
    from app import main, listing_agent
    from app.deps import get_settings
    from app.db import Database
    from app.listing_agent import Agent, Store
    state = upload(client, start(client)).json()
    db = Database(get_settings().database_url)
    queued = []
    monkeypatch.setattr(main, '_enqueue_existing_listing_analysis', lambda **kwargs: queued.append(kwargs))
    try:
        store = Store(db, 'api-key')
        saved = store.load(state['session_id'])
        saved.update(facts=dict(category='clothes', condition='New', size='M'), evidence=dict(status='checked', missing_required=[]))
        saved['approved'] = Agent.version(saved)
        store.save(saved)
        monkeypatch.setattr(listing_agent, 'call_model', scripted(('create_private_draft', {}), ('start_listing_analysis', {})))
        path = f'/v1/listing-agent/sessions/{saved["session_id"]}'
        response = client.post(path + '/turns', headers=AUTH, json=dict(request_id='start', expected_revision=saved['revision'], message='Continue'))
        assert response.status_code == 200, response.text
        assert len(queued) == 1
        client.get(path, headers=AUTH)
        assert len(queued) == 1
        db.execute("UPDATE listing_agent_tools SET updated_at='2000-01-01T00:00:00+00:00' WHERE name='dispatch_analysis'")
        db.commit()
        client.get(path, headers=AUTH)
        assert len(queued) == 2
        assert queued[0]['job_id'] == queued[1]['job_id']
    finally:
        db.close()


def test_uploads_and_client_state_are_not_trusted(client):
    state = start(client)
    assert upload(client, state, b'not-an-image').status_code == 400
    uploaded = upload(client, state).json()
    assert upload(client, state, photo('blue'), 'stale').status_code == 409
    assert upload(client, uploaded, photo('blue'), 'photos').status_code == 409
    path = f'/v1/listing-agent/sessions/{state["session_id"]}/turns'
    for forged in [dict(workflow_stage='review'), dict(listing_id='another-owner'), dict(photo_count=6), dict(approved=True)]:
        result = client.post(path, headers=AUTH, json=dict(request_id='forged', expected_revision=uploaded['revision'], message='publish', **forged))
        assert result.status_code == 422


def test_owner_scoping_and_stale_confirmation(client, monkeypatch):
    from app.auth import AuthPrincipal, get_request_principal
    from app.main import app
    from app import listing_agent
    state = start(client)
    path = f'/v1/listing-agent/sessions/{state["session_id"]}'
    app.dependency_overrides[get_request_principal] = lambda: AuthPrincipal(auth_type='clerk', subject='other', claims={})
    try:
        assert client.get(path).status_code == 404
        assert upload(client, state).status_code == 404
        assert client.post(path + '/turns', json=dict(request_id='attack', expected_revision=0, message='hi')).status_code == 404
    finally:
        app.dependency_overrides.clear()
    result = client.post(path + '/turns', headers=AUTH, json=dict(request_id='stale-confirm',
        expected_revision=state['revision'], message='confirm', confirmation_token='forged'))
    assert result.status_code == 409


def test_photo_addition_invalidates_coverage_and_approval(client):
    from app.deps import get_settings
    from app.listing_agent import Store
    from app.db import Database
    state = start(client)
    state = upload(client, state).json()
    db = Database(get_settings().database_url)
    try:
        store = Store(db, 'api-key')
        saved = store.load(state['session_id'])
        saved.update(evidence={'status': 'checked'}, waivers=['brand_label'], approved='old', pending={'type': 'confirm_analysis'})
        store.save(saved)
        duplicate = upload(client, saved, photo(), 'duplicate-preserves-evidence')
        assert duplicate.status_code == 200, duplicate.text
        saved = store.load(state['session_id'])
        assert saved['evidence'] == {'status': 'checked'}
        assert saved['approved'] == 'old' and saved['waivers'] == ['brand_label']
        response = upload(client, saved, photo('blue'), 'replacement')
        assert response.status_code == 200, response.text
        updated = store.load(state['session_id'])
        assert len(updated['photos']) == 2
        assert updated['photos'][0] == state['photos'][0]
        assert updated['evidence'] is None and updated['approved'] is None and updated['pending'] is None
        assert updated['waivers'] == []
    finally:
        db.close()
