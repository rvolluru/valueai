import asyncio
import json
import pytest
from app.assistant_listing_tools import catalog, validate, AdapterTurn
from app.assistant_read_agent import run
from app.assistant_capabilities import tool_catalog
from test_listing_agent import fixture, Services, scripted
from app.listing_agent import Agent, Store, Turn
from fastapi import HTTPException


def test_catalog_excludes_model_approval_and_disabled_tools():
    names = {t['name'] for t in catalog()}
    assert {'record_user_facts', 'remove_listing_photo', 'start_listing_analysis', 'prepare_trade_request'} <= names
    assert not names & {'publish_listing', 'send_trade_request', 'apply_listing_changes'}
    assert not names & {t['name'] for t in tool_catalog(False)}
    for name in ('publish_listing', 'send_trade_request', 'apply_listing_changes'):
        with pytest.raises(ValueError):
            validate(name, {})
    with pytest.raises(ValueError):
        validate('start_listing_analysis', {'confirmation_token': 'invented'})


def test_internal_request_fingerprint_includes_operation():
    turn = AdapterTurn(request_id='r', expected_revision=0, message='New',
        tool_name='record_user_facts', tool_arguments={'facts': {'condition': 'New'}, 'evidence_quote': 'New'})
    assert turn.model_dump()['tool_name'] == 'record_user_facts'
    assert turn.model_dump()['tool_arguments']['facts']['condition'] == 'New'


def test_parent_reads_context_then_executes_one_guarded_action():
    calls = []
    async def model(*args):
        name, arguments = ('get_listing_context', {}) if not calls else ('record_user_facts',
            {'facts': {'condition': 'New'}, 'evidence_quote': 'New'})
        return {'output': [dict(type='function_call', call_id='x', name=name, arguments=json.dumps(arguments))]}
    async def listing(name, arguments):
        calls.append(name)
        return dict(reply='Saved', result_sets=[], focus=None, workflow_context={'facts': {}})
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None, workflow_id='owned'),
        'New', None, model, listing=listing))
    assert calls == ['get_listing_context', 'record_user_facts']
    assert result['reply'] == 'Saved'


def test_parent_requires_thread_link_and_enabled_adapter():
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='x', name='start_listing_analysis', arguments='{}')]}
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Analyze', None, model))
    assert result['outcome']['category'] == 'blocked'


def test_direct_fact_adapter_reuses_validation_and_ledger(fixture):
    db, store, state, settings, services = fixture
    state['facts']['category'] = 'clothes'
    store.save(state)
    agent = Agent(store, settings, services, scripted())  # No second model may run.
    request = AdapterTurn(request_id='direct', expected_revision=state['revision'], message='New, size M',
        tool_name='record_user_facts', tool_arguments={'facts': {'condition': 'New', 'size': 'M'}, 'evidence_quote': 'New, size M'})
    first = asyncio.run(agent.turn(state['session_id'], request))
    assert first['facts']['condition'] == 'New' and first['facts']['size'] == 'M'
    assert services.created == services.started == 0
    assert asyncio.run(agent.turn(state['session_id'], request)) == first
    changed = request.model_copy(update={'tool_name': 'start_listing_analysis', 'tool_arguments': {}})
    with pytest.raises(HTTPException) as error:
        asyncio.run(agent.turn(state['session_id'], changed))
    assert error.value.status_code == 409
    with pytest.raises(ValueError):
        Turn.model_validate(request.model_dump())  # Public clients cannot inject an internal tool.


def test_direct_create_without_approval_is_blocked(fixture):
    db, store, state, settings, services = fixture
    request = AdapterTurn(request_id='unapproved', expected_revision=state['revision'], message='Create it',
        tool_name='create_private_draft', tool_arguments={})
    with pytest.raises(HTTPException) as error:
        asyncio.run(Agent(store, settings, services, scripted()).turn(state['session_id'], request))
    assert error.value.status_code == 409
    assert services.created == services.started == 0


def test_foreign_child_cannot_be_loaded(fixture):
    db, store, state, settings, services = fixture
    with pytest.raises(HTTPException) as error:
        Store(db, 'different-owner').load(state['session_id'])
    assert error.value.status_code == 404


def test_correction_rejects_shoe_size_for_clothing_without_changing_facts(fixture):
    db, store, state, settings, services = fixture
    state['stage'] = 'review_ready'
    state['facts'] = {'category': 'clothes', 'size': '10'}
    agent = Agent(store, settings, services, scripted())
    request = Turn(request_id='bad-size', expected_revision=state['revision'], message='Change size to US 10.5')
    result = asyncio.run(agent.execute('propose_listing_changes',
        {'facts': {'size': 'US 10.5'}, 'evidence_quote': request.message}, state, request))
    assert result['error'].startswith('Invalid size for clothes. Valid sizes:')
    assert state['facts']['size'] == '10'
    assert not state.get('edit_proposal')


def test_published_size_rejection_reports_not_saved_and_current_value(fixture):
    db, store, state, settings, services = fixture
    state.update(listing_id='published', job_id='complete', stage='published', publication_approval='approved')
    state['facts'] = {'category': 'clothes', 'size': '10'}
    async def status(_):
        return {'status': 'succeeded'}, {'status': 'Active', 'category': 'clothes', 'size': '10'}
    services.analysis_status = status
    agent = Agent(store, settings, services, scripted())
    request = Turn(request_id='published-size', expected_revision=state['revision'], message='change size to 10.5')
    result = asyncio.run(agent.execute('propose_listing_changes',
        {'facts': {'size': '10.5'}, 'evidence_quote': request.message}, state, request))
    assert 'Size change not saved. Current saved size: 10.' in result['error']
    assert 'already published' in result['error']
    assert 'not valid for this category' in result['error']
    assert 'Wait for analysis' not in result['error']
    assert state['facts']['size'] == '10'
