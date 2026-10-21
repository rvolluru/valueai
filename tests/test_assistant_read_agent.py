import asyncio
import json
import pytest
from fastapi import HTTPException
from app.assistant_read_agent import run


@pytest.mark.parametrize('action,listing_id', [('matches', None), ('details', 'target')])
def test_model_scope_and_factual_tool_continuation(action, listing_id):
    seen = []
    async def model(settings, inputs):
        if not seen:
            return {'output': [dict(type='function_call', name='read_listings', call_id='one',
                arguments=json.dumps(dict(action=action, listing_id=listing_id, terms=[])))]}
        assert json.loads(inputs[-1]['output'])['result_sets'][0]['source_listing_id'] == 'source'
        return {'output': [dict(type='message', content=[dict(type='output_text', text='Actual result')])]}
    async def read(args):
        seen.append(args)
        return dict(reply='Read completed', focus='target', result_sets=[dict(source_listing_id='source')])
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'Show matches', read, model))
    assert seen == [dict(action=action, listing_id=listing_id, terms=[])]
    assert result['focus'] == 'target'
    if action == 'details':
        assert result['reply'] == 'Read completed'  # Server's safe fact summary, not a model metadata dump.


def test_identical_tool_loop_stops_without_reexecuting():
    calls = []
    async def model(*args):
        return {'output': [dict(type='function_call', name='read_listings', call_id='one',
            arguments=json.dumps(dict(action='closet', listing_id=None, terms=[])))]}
    async def read(args):
        calls.append(args)
        return dict(reply='Done', result_sets=[], focus=None)
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'closet', read, model))
    assert len(calls) == 1
    assert result['reply'] == 'Done'


def test_unavailable_record_is_not_success():
    outputs = []
    async def model(settings, inputs):
        if not outputs:
            outputs.append(True)
            return {'output': [dict(type='function_call', name='read_listings', call_id='one',
                arguments=json.dumps(dict(action='details', listing_id='foreign', terms=[])))]}
        assert 'error' in json.loads(inputs[-1]['output'])
        return {'output': [dict(type='message', content=[dict(type='output_text', text='Choose an available item.')])]}
    async def read(args): raise HTTPException(404, 'private secret')
    result = asyncio.run(run(None, dict(messages=[], result_sets=[], focus=None), 'details', read, model))
    assert result['result_sets'] == []
    assert result['reply'] == 'That item is not available. Choose an available listing.'
