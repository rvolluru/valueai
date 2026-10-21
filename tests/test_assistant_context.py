import json
import pytest

from test_listing_agent_api import AUTH, client, trade_ready
from test_listing_agent import scripted


def general_model(monkeypatch, *results):
    from app import main
    pending = list(results)
    captured = []
    class Response:
        status_code = 200
        def json(self):
            return {'output': [{'content': [{'type': 'output_text', 'text': json.dumps(pending.pop(0))}]}]}
    class Model:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            captured.append(kwargs['json'])
            return Response()
    monkeypatch.setattr(main.httpx, 'AsyncClient', Model)
    return captured


@pytest.mark.parametrize('photo_message', [
    'show me images of matched item', 'Can I see photos of that match?',
    'Open pictures of the matched listing',
])
def test_matches_then_photo_request_keeps_target_not_reverse_matches(client, monkeypatch, photo_message):
    from app.deps import get_db
    _, state, _ = trade_ready(client, monkeypatch)
    source_id = state['listing_id']
    target_id = state['trade_proposal']['target']['listing_id']
    captured = general_model(monkeypatch,
        dict(intent='show_matches', reply='Matches', listing_reference=source_id),
        # Regression: even an old/wrong model intent must not reverse the search.
        dict(intent='show_matches', reply='Wrong direction', listing_reference=target_id))
    first = client.post('/v1/app-assistant/chat', headers=AUTH, json=dict(
        messages=[dict(role='user', content='Show matches for my coat')])).json()
    assert first['context']['source_listing_id'] == source_id
    assert first['context']['marketplace_result_ids'] == [target_id]
    assert first['context']['selected_listing_id'] == target_id
    second = client.post('/v1/app-assistant/chat', headers=AUTH, json=dict(context=first['context'],
        messages=[dict(role='user', content=photo_message)]))
    assert second.status_code == 200, second.text
    result = second.json()
    assert result['intent'] == 'view_photos'
    assert result['photo_view']['listing_id'] == target_id
    assert result['photo_view']['images']
    assert [item['listing_id'] for item in result['listings']] == [target_id]
    assert result['context']['source_listing_id'] == source_id
    assert 'SYSTEM CAPABILITIES' in captured[1]['instructions']
    assert 'including requests mentioning images or photos' not in captured[1]['instructions']
    assert not get_db().fetchall('SELECT offer_id FROM trade_offers')


def test_plural_matches_do_not_select_a_stale_single_source(client, monkeypatch):
    from app import main
    _, state, _ = trade_ready(client, monkeypatch)
    source_id = state['listing_id']
    calls = []
    def matches(listing_id, **kwargs):
        calls.append(listing_id)
        return {'count': 1, 'items': [dict(listing_id='target', title='Matched coat', owner_subject='other', status='Active')]}
    monkeypatch.setattr(main, 'list_closet_listing_marketplace_matches', matches)
    general_model(monkeypatch, dict(intent='show_tradeable_items', listing_reference='stale-source'))
    response = client.post('/v1/app-assistant/chat', headers=AUTH, json=dict(
        context=dict(selected_listing_id='stale-source', source_listing_id='stale-source'),
        messages=[dict(role='user', content='show me recent matches for my items in marketplace')]))
    assert response.status_code == 200, response.text
    result = response.json()
    assert source_id in calls
    assert result['intent'] == 'show_matches'
    assert 'Which one' not in result['reply']
    assert all(card['match_source_listing_id'] in calls for card in result['listings'])
    assert result['context']['source_listing_id'] is None


def test_plural_match_detection_preserves_single_item_and_photos():
    from app.assistant_context import requests_all_listing_matches
    assert requests_all_listing_matches('Find matches for my listings')
    assert not requests_all_listing_matches('Find matches for my jacket')
    assert not requests_all_listing_matches('Show photos of matched item')


def test_photo_context_is_ambiguous_until_selection_and_keeps_source_separate():
    from app.main import _app_assistant_photo_target
    from app.schemas import AppAssistantContext
    own = dict(listing_id='source', title='Source coat', owner_subject='me')
    targets = [dict(listing_id='a', title='First jacket'), dict(listing_id='b', title='Second jacket')]
    context = AppAssistantContext(result_listing_ids=['a', 'b'], marketplace_result_ids=['a', 'b'],
        source_listing_id='source', selected_listing_id='source', displayed_domain='marketplace')
    item, choices = _app_assistant_photo_target({'listing_reference': 'source'}, context, [own, *targets], 'Show images of matched item')
    assert item is None and choices == targets
    item, choices = _app_assistant_photo_target({'listing_reference': 'a'}, context, [own, *targets], 'Show images of matched item')
    assert item is None and choices == targets  # A guessed first result is not a user selection.
    item, _ = _app_assistant_photo_target({'listing_reference_index': 2, 'listing_reference_scope': 'marketplace'},
        context, [own, *targets], 'Show photos of second item')
    assert item['listing_id'] == 'b'
    item, _ = _app_assistant_photo_target({}, context, [own, *targets], 'Show photos of my item')
    assert item['listing_id'] == 'source'


def test_private_target_and_foreign_session_context_cannot_disclose_photos(client, monkeypatch):
    from app.deps import get_db
    _, state, _ = trade_ready(client, monkeypatch)
    target_id = state['trade_proposal']['target']['listing_id']
    db = get_db()
    db.execute('UPDATE listings SET status=? WHERE listing_id=?', ('Review', target_id))
    db.commit()
    captured = general_model(monkeypatch, dict(intent='view_photos', listing_reference=target_id))
    response = client.post('/v1/app-assistant/chat', headers=AUTH, json=dict(
        context=dict(result_listing_ids=[target_id], selected_listing_id=target_id,
            listing_agent_session_id='not-owned-session', listing_stage='published', pending_operation='trade_confirmation'),
        messages=[dict(role='user', content='Show photos of that item')]))
    assert response.status_code == 200, response.text
    assert response.json()['photo_view'] is None
    assert not response.json()['listings']
    assert response.json()['context']['listing_agent_session_id'] is None
    assert 'Matched jacket' not in captured[0]['input']


@pytest.mark.parametrize('model_tool', ['view_listing_photos', 'find_marketplace_matches', 'send_trade_request'])
def test_agent_photo_read_exports_focus_and_preserves_pending_trade_approval(client, monkeypatch, model_tool):
    from app import listing_agent
    from app.deps import get_db
    path, state, _ = trade_ready(client, monkeypatch)
    target = state['trade_proposal']['target']['listing_id']
    monkeypatch.setattr(listing_agent, 'call_model', scripted((model_tool, {'listing_id': None} if model_tool == 'view_listing_photos' else {})))
    response = client.post(path, headers=AUTH, json=dict(request_id='photo-read', expected_revision=state['revision'],
        message='Show me images of matched item'))
    assert response.status_code == 200, response.text
    viewed = response.json()
    assert viewed['photo_view']['listing_id'] == target
    context = viewed['conversation_context']
    assert context['source_listing_id'] == state['listing_id']
    assert context['selected_listing_id'] == target
    assert context['pending_operation'] == 'trade_confirmation'
    assert 'token' not in json.dumps(context)
    assert viewed['trade_proposal']['token'] == state['trade_proposal']['token']
    assert not get_db().fetchall('SELECT offer_id FROM trade_offers')
    assert 'photo_view' not in client.get(path.removesuffix('/turns'), headers=AUTH).json()
    general_model(monkeypatch, dict(intent='view_photos', listing_reference=None))
    handed_back = client.post('/v1/app-assistant/chat', headers=AUTH, json=dict(context=context,
        messages=[dict(role='user', content='Show me images of matched item')]))
    assert handed_back.status_code == 200, handed_back.text
    assert handed_back.json()['photo_view']['listing_id'] == target
    assert handed_back.json()['context']['source_listing_id'] == state['listing_id']
    assert get_db().get_listing_by_id(state['listing_id'])['estimated_value'] == 123
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1


def test_readonly_photo_request_has_no_publish_or_trade_permission(client, monkeypatch):
    path, state, _ = trade_ready(client, monkeypatch)
    response = client.post(path, headers=AUTH, json=dict(request_id='photo-permission-mix', expected_revision=state['revision'],
        message='Show photos', photo_listing_id=state['listing_id'], trade_token=state['trade_proposal']['token']))
    assert response.status_code == 400


@pytest.mark.parametrize('message,expected', [
    ('Show me images of matched item', True), ('Can I see its photos?', True),
    ('Find matches with photos', False), ('Show matches with photos', False),
    ('Show me matched listings with images', False),
    ('Remove this photo', False), ('Upload photos', False),
])
def test_photo_view_is_distinct_from_search_and_image_mutation(message, expected):
    from app.assistant_context import requests_photo_view
    assert requests_photo_view(message) is expected


def test_agent_reads_real_item_details_without_reanalysis(client, monkeypatch):
    from app import listing_agent
    from app.deps import get_db
    path, state, _ = trade_ready(client, monkeypatch)
    monkeypatch.setattr(listing_agent, 'call_model', scripted(('view_listing_details', {'listing_id': None})))
    response = client.post(path, headers=AUTH, json=dict(request_id='read-item-details', expected_revision=state['revision'],
        message='Tell me about that item'))
    assert response.status_code == 200, response.text
    assert 'Matched jacket' in response.json()['reply']
    assert '$123' in response.json()['reply']
    assert len(get_db().fetchall('SELECT job_id FROM listing_analysis_jobs')) == 1
    assert not get_db().fetchall('SELECT offer_id FROM trade_offers')


def test_item_summary_fits_followup_history_and_does_not_invent_a_value():
    from app.assistant_context import listing_detail_summary
    assert len(listing_detail_summary({'description': 'x' * 4000})) <= 2000
    assert 'Value needs review' in listing_detail_summary({'estimated_value': 0})
