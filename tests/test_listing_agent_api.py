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


def upload(client, state, data=None, request='photos'):
    return client.post(f'/v1/listing-agent/sessions/{state["session_id"]}/photos', headers=AUTH,
        data={'request_id': request, 'expected_revision': state['revision']},
        files=[('images', ('photo.jpg', data or photo(), 'image/jpeg'))])


def test_disabled_route_and_auth_required(client, monkeypatch):
    from app.deps import get_settings
    assert client.post('/v1/listing-agent/sessions', json={'request_id': 'x'}).status_code == 401
    monkeypatch.setattr(get_settings(), 'listing_agent_enabled', False)
    assert client.post('/v1/listing-agent/sessions', headers=AUTH, json={'request_id': 'x'}).status_code == 404


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
    assert upload(client, resumed, request='changed-after-draft').status_code == 409
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


def test_photo_replacement_invalidates_coverage_and_approval(client):
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
        response = upload(client, saved, photo('blue'), 'replacement')
        assert response.status_code == 200, response.text
        updated = store.load(state['session_id'])
        assert updated['evidence'] is None and updated['approved'] is None and updated['pending'] is None
        assert updated['waivers'] == []
    finally:
        db.close()
