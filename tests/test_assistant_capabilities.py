import asyncio
import json
import pytest
from pydantic import ValidationError
from app.assistant_capabilities import CAPABILITIES, ReadArguments, outcome, tool_catalog
from app.assistant_read_agent import run
from fastapi import HTTPException


@pytest.mark.parametrize('status,category,retryable', [
    ('clarification', 'unclear', False), ('unsupported', 'unsupported', False),
    ('ineligible', 'blocked', False), ('unavailable', 'blocked', False),
    ('tool_failure', 'tool_failure', True), ('no_matches', 'result', False),
])
def test_outcome_categories_are_not_interchangeable(status, category, retryable):
    result = outcome(status)
    assert result['category'] == category and result['retryable'] == retryable


@pytest.mark.parametrize('status,expected', [(403, 'blocked'), (404, 'blocked'), (422, 'unclear'), (503, 'tool_failure')])
def test_real_tool_errors_are_not_invented_missing_capabilities(status, expected):
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='read', name='read_listings',
            arguments=json.dumps(dict(action='details', listing_id='item', terms=[])))]}
    async def read(args): raise HTTPException(status, 'sensitive internal error')
    if status == 503:
        with pytest.raises(HTTPException) as error:
            asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Details', read, model))
        assert error.value.status_code == 503
        assert error.value.headers['X-Assistant-Outcome'] == 'tool_failure'
        assert 'sensitive' not in error.value.detail
    else:
        result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Details', read, model))
        assert result['outcome']['category'] == expected
        assert 'sensitive' not in result['reply']


def test_catalog_and_runtime_arguments_agree():
    actions = tool_catalog()[0]['parameters']['properties']['action']['enum']
    assert set(actions) == set(CAPABILITIES)
    for action in actions:
        ReadArguments(action=action, result_set_id='set-id' if action == 'more' else None)
    for args in [dict(action='matches', terms=['similar brands']),
                 dict(action='matches', tolerance=10000), dict(action='search', price_range=[0, 100]),
                 dict(action='publish'), dict(action='search', listing_id='id')]:
        with pytest.raises(ValidationError): ReadArguments(**args)


@pytest.mark.parametrize('message', [
    'Are there matches for this listing?', 'Find similar-value trade matches',
    'Show matches for my items', 'Refresh eligible matches',
])
def test_no_match_reply_cannot_be_expanded_by_model(message):
    calls = []
    async def model(*args):
        calls.append(True)
        if len(calls) > 1:
            raise AssertionError('Matching result must terminate before unsupported prose')
        return {'output': [dict(type='function_call', call_id='match', name='read_listings',
            arguments=json.dumps(dict(action='matches', listing_id=None, terms=[])))]}
    async def read(args):
        return dict(reply='No eligible Marketplace matches are available right now.', result_sets=[], focus=None,
            outcome=outcome('no_matches', [dict(action='matches', label='Refresh matches')]))
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), message, read, model))
    assert result['outcome']['status'] == 'no_matches'
    assert 'broaden' not in result['reply']
    assert len(calls) == 1


def test_unsupported_free_prose_is_not_published():
    async def model(*args):
        return {'output': [dict(type='message', content=[dict(type='output_text',
            text='I changed your price and broadened matching criteria. Would you like to pay?')])]}
    async def read(args): raise AssertionError('No tool should execute')
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Broaden rules', read, model))
    assert result['outcome']['category'] == 'unclear'
    assert 'I changed' not in result['reply']


def test_clarification_tool_does_not_accept_model_action_injection():
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='ask', name='request_input',
            arguments=json.dumps(dict(reason='choose_listing', next_action='relax_rules')))]}
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'That item', None, model))
    assert result['outcome']['category'] == 'unclear'
    assert all(a['action'] in CAPABILITIES for a in result['outcome']['next_actions'])


@pytest.mark.parametrize('reason,category', [('choose_task', 'unclear'), ('search_terms', 'unclear'), ('unsupported', 'unsupported')])
def test_explicit_model_pause_reasons_are_preserved(reason, category):
    async def model(*args):
        return {'output': [dict(type='function_call', call_id='ask', name='request_input',
            arguments=json.dumps(dict(reason=reason)))]}
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Request', None, model))
    assert result['outcome']['category'] == category


def test_premature_clarification_recovers_with_targeted_lookup():
    calls = []
    async def model(settings, inputs):
        calls.append(True)
        if len(calls) == 1:
            return {'output': [dict(type='function_call', name='request_input', call_id='ask',
                arguments=json.dumps(dict(reason='choose_listing')))]}
        assert 'First try lookup' in inputs[-1]['output']
        return {'output': [dict(type='function_call', name='read_listings', call_id='find',
            arguments=json.dumps(dict(action='lookup', listing_id=None, terms=['Chanel', 'shoes'])))]}
    reads = []
    async def read(args):
        reads.append(args)
        return dict(reply='Quilted CC Loafers', focus='chanel', result_sets=[], outcome=outcome('available'))
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Details of Chanel shoes', read, model))
    assert result['focus'] == 'chanel'
    assert reads[0]['terms'] == ['Chanel', 'shoes']
    assert len(calls) == 2
