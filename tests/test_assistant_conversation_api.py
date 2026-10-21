from test_listing_agent_api import client, AUTH, trade_ready
import json
import pytest


def test_pending_trade_pages_preserve_status_filter(client, monkeypatch):
    from app.deps import get_settings
    from app.db import Database
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    offers = [dict(offer_id=f'accepted-{i}', status='accepted', from_subject='api-key', to_subject='other') for i in range(8)] + [
        dict(offer_id=f'pending-{i}', status='pending', from_subject='api-key', to_subject='other') for i in range(14)]
    monkeypatch.setattr(Database, 'list_trade_offers_for_subject', lambda *args, **kwargs: offers)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'pending-pages'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/turns'
    first = client.post(path, headers=AUTH, json=dict(request_id='pending-first', expected_revision=0,
        message='Show pending trades', action='pending_trades'))
    assert first.status_code == 200, first.text
    group = first.json()['result_sets'][0]
    assert group['domain'] == 'trades' and group['count'] == 14 and len(group['items']) == 12
    assert group['query']['action'] == 'pending_trades'
    assert all(item['status'] == 'pending' for item in group['items'])
    more = client.post(path, headers=AUTH, json=dict(request_id='pending-more', expected_revision=1,
        message='More pending trades', action='more', result_set_id=group['id']))
    assert more.status_code == 200, more.text
    assert len(more.json()['result_sets'][0]['items']) == 2
    assert all(item['status'] == 'pending' for item in more.json()['result_sets'][0]['items'])


def test_parent_direct_listing_action_uses_link_and_replays_without_model(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent, listing_agent
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    selected = [('listing_workflow', dict(mode='start', listing_id=None))]
    calls = []
    async def model(*args):
        name, arguments = selected[-1]
        calls.append(name)
        return {'output': [dict(type='function_call', call_id='tool', name=name, arguments=json.dumps(arguments))]}
    async def forbidden_child_model(*args):
        raise AssertionError('A direct adapter must not invoke another model')
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    monkeypatch.setattr(listing_agent, 'call_model', forbidden_child_model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'direct-parent'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/messages'
    opened = client.post(path, headers=AUTH, json=dict(request_id='open', expected_revision=0, message='Create listing')).json()
    selected.append(('record_user_facts', dict(facts={'condition': 'New'}, evidence_quote='New')))
    payload = dict(request_id='fact', expected_revision=1, message='New')
    result = client.post(path, headers=AUTH, json=payload)
    assert result.status_code == 200, result.text
    child = client.get('/v1/listing-agent/sessions/' + opened['workflow_id'], headers=AUTH).json()
    assert child['facts']['condition'] == 'New'
    assert not child['listing_id']
    count = len(calls)
    assert client.post(path, headers=AUTH, json=payload).json() == result.json()
    assert len(calls) == count
    assert result.json()['pending'] is None  # Approval capabilities remain child-local.


def test_domain_validation_is_a_saved_blocked_reply_not_a_false_revision_conflict(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent, assistant_listing_tools
    from fastapi import HTTPException
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    selected = [('listing_workflow', dict(mode='start', listing_id=None))]
    async def model(*args):
        name, arguments = selected[-1]
        return {'output': [dict(type='function_call', call_id='tool', name=name, arguments=json.dumps(arguments))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'blocked-parent'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/messages'
    client.post(path, headers=AUTH, json=dict(request_id='start', expected_revision=0, message='Create listing'))
    selected.append(('propose_listing_changes', dict(facts={'size': 'US 10.5'}, evidence_quote='Change size to US 10.5')))
    async def blocked(*args, **kwargs):
        raise HTTPException(409, 'Invalid size for clothes. Valid sizes: S, M, L', headers={'X-Assistant-Outcome': 'blocked'})
    monkeypatch.setattr(assistant_listing_tools, 'execute', blocked)
    payload = dict(request_id='invalid-size', expected_revision=1, message='Change size to US 10.5')
    result = client.post(path, headers=AUTH, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['outcome']['category'] == 'blocked'
    assert result.json()['messages'][-1]['content'] == 'Invalid size for clothes. Valid sizes: S, M, L'
    assert client.post(path, headers=AUTH, json=payload).json() == result.json()


def test_closet_paging_preserves_query_and_retry_without_accepting_an_offset(client, monkeypatch):
    from app.deps import get_settings
    from app.db import Database
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    items = [dict(listing_id=f'item-{i}', title=f'Coat {i}', owner_subject='api-key', status='Active', estimated_value=100) for i in range(25)]
    monkeypatch.setattr(Database, 'list_owner_listings', lambda *args, **kwargs: items)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'paging'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/turns'
    first = client.post(path, headers=AUTH, json=dict(request_id='browse', expected_revision=0, message='Closet', action='closet')).json()
    group = first['result_sets'][0]
    assert len(group['items']) == 12 and group['next_offset'] == 12
    more = dict(request_id='page-two', expected_revision=1, message='More items', action='more', result_set_id=group['id'])
    response = client.post(path, headers=AUTH, json=more)
    assert response.status_code == 200, response.text
    second = response.json()
    assert second['result_sets'][0]['offset'] == 12
    assert second['result_sets'][0]['items'][0]['listing_id'] == 'item-12'
    assert client.post(path, headers=AUTH, json=more).json() == second
    assert client.post(path, headers=AUTH, json={**more, 'request_id': 'forged', 'expected_revision': 2, 'offset': 999}).status_code == 422
    assert client.post(path, headers=AUTH, json={**more, 'request_id': 'foreign-set', 'expected_revision': 2, 'result_set_id': 'other-thread-result'}).status_code == 409


def test_match_paging_uses_same_source_and_backend_rules(client, monkeypatch):
    from app.deps import get_settings
    from app import main
    _, source, _ = trade_ready(client, monkeypatch)
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    calls = []
    def page(key, limit, offset, **kwargs):
        calls.append((key, limit, offset))
        rows = [dict(listing_id=f'match-{i}', title=f'Match {i}', owner_subject='other', status='Active') for i in range(7)]
        return dict(count=7, items=rows[offset:offset+limit], has_more=offset+limit < 7,
                    next_offset=offset+limit if offset+limit < 7 else None)
    monkeypatch.setattr(main, 'list_closet_listing_marketplace_matches', page)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'match-paging'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/turns'
    first = client.post(path, headers=AUTH, json=dict(request_id='matches', expected_revision=0,
        message='Matches', action='matches', listing_id=source['listing_id'])).json()
    response = client.post(path, headers=AUTH, json=dict(request_id='next', expected_revision=1,
        message='More matches', action='more', result_set_id=first['result_sets'][0]['id']))
    assert response.status_code == 200, response.text
    assert calls == [(source['listing_id'], 3, 0), (source['listing_id'], 3, 3)]
    assert response.json()['result_sets'][0]['source_listing_id'] == source['listing_id']


def test_preferences_read_is_sanitized_and_read_only(client, monkeypatch):
    from app.deps import get_settings
    from app.db import Database
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    monkeypatch.setattr(Database, 'get_user_profile_quiz', lambda *args: dict(tops_size='M',
        category_preferences=['shoes'], email='NEVER-EXPOSE', shipping_phone='NEVER-EXPOSE'))
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'preferences'}).json()['conversation_id']
    response = client.post(f'/v1/assistant-conversations/{key}/turns', headers=AUTH,
        json=dict(request_id='prefs', expected_revision=0, message='My matching preferences', action='preferences'))
    assert response.status_code == 200, response.text
    assert 'NEVER-EXPOSE' not in response.text
    assert 'Tops size: M' in response.json()['messages'][-1]['content']


def test_parent_starts_fresh_child_and_resumes_exact_link_without_analysis(client, monkeypatch):
    from app.deps import get_settings, get_db
    from app import assistant_read_agent
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    mode = ['start']
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='workflow', name='listing_workflow',
            arguments=json.dumps(dict(mode=mode[0], listing_id=None)))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'workflow-parent'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}'
    payload = dict(request_id='new-workflow', expected_revision=0, message='Create a new listing')
    first = client.post(path + '/messages', headers=AUTH, json=payload)
    assert first.status_code == 200, first.text
    child_id = first.json()['workflow_id']
    assert child_id
    assert client.post(path + '/messages', headers=AUTH, json=payload).json() == first.json()
    child = client.get('/v1/listing-agent/sessions/' + child_id, headers=AUTH).json()
    assert not child['listing_id'] and not child['photos']
    assert 'confirmation_token' not in first.json()
    mode[0] = 'resume'
    resumed = client.post(path + '/messages', headers=AUTH, json=dict(
        request_id='resume-workflow', expected_revision=1, message='Resume my listing'))
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['workflow_id'] == child_id
    mode[0] = 'start'
    new = client.post(path + '/messages', headers=AUTH, json=dict(
        request_id='another-item', expected_revision=2, message='Create another new listing'))
    assert new.status_code == 200, new.text
    assert new.json()['workflow_id'] != child_id
    assert get_db().fetchone('SELECT COUNT(*) FROM listings')[0] == 0
    assert get_db().fetchone('SELECT COUNT(*) FROM listing_analysis_jobs')[0] == 0
    assert get_db().fetchone('SELECT COUNT(*) FROM trade_offers')[0] == 0


def test_workflow_start_retries_after_link_checkpoint_failure_without_duplicate_child(client, monkeypatch):
    from app.deps import get_settings, get_db
    from app import assistant_read_agent
    from app.assistant_conversations import ConversationStore
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='workflow', name='listing_workflow',
            arguments=json.dumps(dict(mode='start', listing_id=None)))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'checkpoint'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/messages'
    payload = dict(request_id='same-operation', expected_revision=0, message='Create listing')
    original = ConversationStore.commit_turn
    def interrupted(*args, **kwargs): raise RuntimeError('lost checkpoint')
    monkeypatch.setattr(ConversationStore, 'commit_turn', interrupted)
    with pytest.raises(RuntimeError): client.post(path, headers=AUTH, json=payload)
    assert get_db().fetchone('SELECT COUNT(*) FROM listing_agent_sessions')[0] == 1
    monkeypatch.setattr(ConversationStore, 'commit_turn', original)
    result = client.post(path, headers=AUTH, json=payload)
    assert result.status_code == 200, result.text
    assert get_db().fetchone('SELECT COUNT(*) FROM listing_agent_sessions')[0] == 1


def test_resume_does_not_adopt_unrelated_active_session(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    client.post('/v1/listing-agent/sessions', headers=AUTH, json={'request_id': 'unrelated'})
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='workflow', name='listing_workflow',
            arguments=json.dumps(dict(mode='resume', listing_id=None)))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'empty-parent'}).json()['conversation_id']
    result = client.post(f'/v1/assistant-conversations/{key}/messages', headers=AUTH,
        json=dict(request_id='resume', expected_revision=0, message='Resume listing'))
    assert result.status_code == 200, result.text
    assert result.json()['workflow_id'] is None
    assert result.json()['outcome']['category'] == 'unclear'


def test_workflow_handoff_cannot_open_another_owners_listing(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent
    _, source, _ = trade_ready(client, monkeypatch)
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    target = source['trade_proposal']['target']['listing_id']
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='workflow', name='listing_workflow',
            arguments=json.dumps(dict(mode='resume', listing_id=target)))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'owner-guard'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}'
    result = client.post(path + '/messages', headers=AUTH, json=dict(request_id='foreign', expected_revision=0, message='Review this listing'))
    assert result.status_code == 404
    assert client.get(path, headers=AUTH).json()['workflow_id'] is None


def test_workflow_tool_is_unavailable_when_listing_agent_is_disabled(client, monkeypatch):
    from app.deps import get_settings, get_db
    from app import assistant_read_agent
    from app.assistant_capabilities import tool_catalog
    settings = get_settings()
    monkeypatch.setattr(settings, 'assistant_conversations_enabled', True)
    monkeypatch.setattr(settings, 'listing_agent_enabled', False)
    assert not any(t['name'] == 'listing_workflow' for t in tool_catalog(False))
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='workflow', name='listing_workflow',
            arguments=json.dumps(dict(mode='start', listing_id=None)))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'disabled'}).json()['conversation_id']
    result = client.post(f'/v1/assistant-conversations/{key}/messages', headers=AUTH,
        json=dict(request_id='new', expected_revision=0, message='Create listing'))
    assert result.status_code == 200
    assert result.json()['outcome']['category'] == 'unsupported'
    assert result.json()['workflow_id'] is None
    assert get_db().fetchone('SELECT COUNT(*) FROM listing_agent_sessions')[0] == 0


def test_temporary_read_failure_is_retryable_without_committing_a_turn(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent, assistant_conversation_routes
    from fastapi import HTTPException
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'failure'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}'
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='read', name='read_listings',
            arguments=json.dumps(dict(action='closet', listing_id=None, terms=[])))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    def fail(*args, **kwargs): raise HTTPException(503, 'secret provider trace')
    monkeypatch.setattr(assistant_conversation_routes, 'execute_read', fail)
    payload = dict(request_id='same-retry', expected_revision=0, message='My closet')
    for _ in range(2):
        response = client.post(path + '/messages', headers=AUTH, json=payload)
        assert response.status_code == 503
        assert response.headers['x-assistant-outcome'] == 'tool_failure'
        assert 'secret' not in response.text
    assert client.get(path, headers=AUTH).json()['revision'] == 0


@pytest.mark.parametrize('duplicate,terms,count', [(False, ['Chanel', 'shoes'], 1), (True, ['Chanel', 'shoes'], 2), (False, ['NonexistentBrand'], 0)])
def test_named_closet_lookup_only_shows_relevant_owned_choices(client, monkeypatch, duplicate, terms, count):
    from app.deps import get_settings, get_db
    _, source, _ = trade_ready(client, monkeypatch)
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    db = get_db()
    db.execute('UPDATE listings SET title=?,category=? WHERE listing_id=?', ('Quilted CC Loafers', 'shoes', source['listing_id']))
    db.execute('UPDATE listings SET category=? WHERE owner_subject=?', ('shoes', 'other-seller'))
    db.commit()
    if duplicate:
        created = client.post('/v1/listings', headers=AUTH, json=dict(title='Chanel Ballet Flats', brand='Chanel',
            category='shoes', condition='New', size='US 10', estimated_value=123, status='Review',
            image=source['photos'][0]['url'], images=[source['photos'][0]['url']]))
        assert created.status_code == 200, created.text
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'lookup'}).json()['conversation_id']
    response = client.post(f'/v1/assistant-conversations/{key}/turns', headers=AUTH,
        json=dict(request_id='read', expected_revision=0, message='show me details of chanel shoes listing', action='lookup', terms=terms))
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['result_sets'][0]['count'] == count
    if count == 1:
        assert state['focus'] == source['listing_id']
        assert 'Quilted CC Loafers' in state['messages'][-1]['content']
    else:
        assert state['focus'] is None
        assert state['outcome']['status'] == ('clarification' if count else 'empty')


@pytest.mark.parametrize('source_active,match_count,expected', [(True, 0, 'no_matches'), (False, 0, 'ineligible'), (True, 5, 'more_available')])
def test_matching_outcomes_and_followup_choices_are_fixed(client, monkeypatch, source_active, match_count, expected):
    from app.deps import get_settings, get_db
    from app import main, assistant_read_agent
    _, source, _ = trade_ready(client, monkeypatch)
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'outcomes'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}'
    if not source_active:
        get_db().execute('UPDATE listings SET status=? WHERE listing_id=?', ('Review', source['listing_id']))
        get_db().commit()
    target = dict(listing_id='public', title='Actual target', owner_subject='other', status='Active')
    monkeypatch.setattr(main, 'list_closet_listing_marketplace_matches', lambda *args, **kw: dict(
        count=match_count, items=[target] if match_count else [], has_more=match_count > 1))
    # Two turns: select source details, then find matches. Inject unsupported prose
    # after the tool call; it must never become the user-visible reply.
    details = client.post(path + '/turns', headers=AUTH, json=dict(request_id='details', expected_revision=0,
        message='Review this item', action='details', listing_id=source['listing_id']))
    assert details.status_code == 200
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='match', name='read_listings',
            arguments=json.dumps(dict(action='matches', listing_id=source['listing_id'], terms=[])))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    result = client.post(path + '/messages', headers=AUTH, json=dict(request_id='match', expected_revision=1,
        message='Are there matches for this listing?'))
    assert result.status_code == 200, result.text
    state = result.json()
    assert state['outcome']['status'] == expected
    assert state['outcome']['rules_fixed']
    assert all(a['action'] in {'matches', 'closet'} for a in state['outcome']['next_actions'])
    if not source_active:
        assert not any(a['action'] == 'matches' for a in state['outcome']['next_actions'])
    invalid = client.post(path + '/turns', headers=AUTH, json=dict(request_id='relax', expected_revision=2,
        message='Broaden matching', action='matches', listing_id=source['listing_id'], terms=['broader']))
    assert invalid.status_code == 422
    assert client.get(path, headers=AUTH).json()['revision'] == 2


def test_thread_list_is_owned_and_new_threads_are_empty(client, monkeypatch):
    from app.deps import get_settings, get_db
    from app.assistant_conversations import ConversationStore
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    a = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'thread-a'}).json()
    b = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'thread-b'}).json()
    assert a['conversation_id'] != b['conversation_id']
    assert b['messages'] == [] and b['focus'] is None
    foreign = ConversationStore(get_db(), 'another-owner').create('foreign')['conversation_id']
    response = client.get('/v1/assistant-conversations', headers=AUTH)
    assert response.status_code == 200, response.text
    ids = [item['conversation_id'] for item in response.json()['items']]
    assert a['conversation_id'] in ids and b['conversation_id'] in ids and foreign not in ids
    assert client.get('/v1/assistant-conversations/' + foreign, headers=AUTH).status_code == 404


def test_gallery_message_emits_once_and_does_not_reopen_on_resume(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent
    _, source, _ = trade_ready(client, monkeypatch)
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'gallery'}).json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}'
    seeded = client.post(path + '/turns', headers=AUTH, json=dict(request_id='focus', expected_revision=0,
        message='Details', action='details', listing_id=source['listing_id']))
    assert seeded.status_code == 200, seeded.text
    calls = []
    async def model(*args):
        calls.append(True)
        return {'output': [dict(type='function_call', name='read_listings', call_id='photos',
            arguments=json.dumps(dict(action='photos', listing_id=None, terms=[])))]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    payload = dict(request_id='gallery-open', expected_revision=1, message='yes, show me image gallery')
    result = client.post(path + '/messages', headers=AUTH, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['gallery']['listing']['images']
    assert result.json()['gallery']['listing']['listing_id'] == source['listing_id']
    assert result.json()['messages'][-1]['content'] == 'Opening the image gallery.'
    assert client.post(path + '/messages', headers=AUTH, json=payload).json() == result.json()
    assert len(calls) == 1
    assert 'gallery' not in client.get(path, headers=AUTH).json()


def test_model_read_loop_and_committed_retry(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'model'}).json()['conversation_id']
    captured = []
    async def model(settings, inputs):
        captured.append(list(inputs))
        if len(captured) == 1:
            return {'output': [dict(type='function_call', name='read_listings', call_id='read',
                arguments=json.dumps(dict(action='closet', listing_id=None, terms=[])))]}
        assert inputs[-1]['type'] == 'function_call_output'
        return {'output': [dict(type='message', content=[dict(type='output_text', text='Here is your closet.')])]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    path = f'/v1/assistant-conversations/{key}/messages'
    payload = dict(request_id='message', expected_revision=0, message='Show my items')
    first = client.post(path, headers=AUTH, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()['messages'][-1]['content'] == 'Your closet is empty.'
    assert first.json()['result_sets'][0]['domain'] == 'closet'
    assert client.post(path, headers=AUTH, json=payload).json() == first.json()
    assert len(captured) == 2


def test_model_cannot_request_a_write(client, monkeypatch):
    from app.deps import get_settings
    from app import assistant_read_agent
    monkeypatch.setattr(get_settings(), 'assistant_conversations_enabled', True)
    key = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'bad-model'}).json()['conversation_id']
    async def model(*args):
        return {'output': [dict(type='function_call', name='publish_listing', call_id='bad', arguments='{}')]}
    monkeypatch.setattr(assistant_read_agent, 'call_model', model)
    response = client.post(f'/v1/assistant-conversations/{key}/messages', headers=AUTH,
        json=dict(request_id='bad', expected_revision=0, message='Publish everything'))
    assert response.status_code == 502
    assert client.get(f'/v1/assistant-conversations/{key}', headers=AUTH).json()['revision'] == 0


def test_read_pilot_flag_and_retry_contract(client, monkeypatch):
    from app.deps import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'assistant_conversations_enabled', False)
    assert client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'start'}).status_code == 404
    monkeypatch.setattr(settings, 'assistant_conversations_enabled', True)
    created = client.post('/v1/assistant-conversations', headers=AUTH, json={'request_id': 'start'})
    assert created.status_code == 200, created.text
    key = created.json()['conversation_id']
    path = f'/v1/assistant-conversations/{key}/turns'
    payload = dict(request_id='read', expected_revision=0, message='Show my closet', action='closet')
    first = client.post(path, headers=AUTH, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()['result_sets'][0]['domain'] == 'closet'
    assert client.post(path, headers=AUTH, json=payload).json() == first.json()
    assert client.post(path, headers=AUTH, json={**payload, 'message': 'different'}).status_code == 409
    assert client.post(path, headers=AUTH, json={**payload, 'request_id': 'next'}).status_code == 409
    assert client.post(path, headers=AUTH, json={**payload, 'action': 'publish'}).status_code == 422
    assert client.post(path, headers=AUTH, json={**payload, 'approval': True}).status_code == 422
    assert client.get(f'/v1/assistant-conversations/{key}', headers=AUTH).json()['revision'] == 1
