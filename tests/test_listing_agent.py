import asyncio
import copy
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.db import Database
from app.listing_agent import Agent, Store, Turn, tools


def run(awaitable):
    return asyncio.run(awaitable)


class Services:
    def __init__(self):
        self.created = 0
        self.started = 0
        self.assessed = 0
        self.status = 'queued'

    async def assess(self, state):
        self.assessed += 1
        return dict(status='checked', category='clothes', category_confidence=.95, missing_required=[])

    async def create_draft(self, state):
        self.created += 1
        return {'listing_id': 'draft-one'}

    async def start_analysis(self, state):
        self.started += 1
        return {'job_id': 'job-one', 'status': self.status}

    async def analysis_status(self, state):
        return ({'job_id': 'job-one', 'status': self.status},
                {'listing_id': 'draft-one', 'status': 'Review', 'estimated_value': 150})


def scripted(*calls):
    pending = list(calls)
    captured = []
    async def model(settings, inputs):
        captured.append(copy.deepcopy(inputs))
        name, args = pending.pop(0)
        return {'output': [dict(type='function_call', call_id=f'call-{len(captured)}',
                                name=name, arguments=json.dumps(args))]}
    model.captured = captured
    return model


@pytest.fixture
def fixture(tmp_path):
    db = Database(f'sqlite:///{tmp_path / "agent.db"}')
    db.initialize()
    store = Store(db, 'owner-a')
    state = store.create('start-one')
    state['photos'] = [dict(image_id='img', item_id='owned-item', url='/v1/images/img', content_hash='photo-a')]
    store.save(state)
    settings = SimpleNamespace(listing_agent_max_steps=6, listing_agent_turn_timeout_s=10)
    services = Services()
    yield db, store, state, settings, services
    db.close()


def turn(state, request='message-one', message='New with tags, size M', **kwargs):
    return Turn(request_id=request, expected_revision=state['revision'], message=message, **kwargs)


def prepare(fixture):
    db, store, state, settings, services = fixture
    model = scripted(('assess_photo_evidence', {}),
        ('record_user_facts', {'facts': {'condition': 'NewWithTags', 'size': 'M'}, 'evidence_quote': 'New with tags, size M'}),
        ('prepare_analysis_confirmation', {}))
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state)))
    return result, model


def test_agent_chooses_tools_observes_results_then_pauses_for_confirmation(fixture):
    db, store, state, settings, services = fixture
    result, model = prepare(fixture)
    assert result['pending']['type'] == 'confirm_analysis'
    assert result['facts'] == dict(category='clothes', condition='NewWithTags', size='M')
    assert services.created == services.started == 0
    outputs = [i for i in model.captured[-1] if i.get('type') == 'function_call_output']
    assert len(outputs) == 2
    assert json.loads(outputs[0]['output'])['status'] == 'checked'


def test_explicit_confirmation_starts_one_draft_and_replay_calls_no_model(fixture):
    db, store, state, settings, services = fixture
    prepared, _ = prepare(fixture)
    model = scripted(('create_private_draft', {}), ('start_listing_analysis', {}))
    agent = Agent(store, settings, services, model)
    request = turn(prepared, 'confirmation', 'Confirm private draft', confirmation_token=prepared['pending']['token'])
    result = run(agent.turn(state['session_id'], request))
    assert result['stage'] == 'analyzing'
    assert services.created == services.started == 1
    assert 'not been published' in result['reply']
    assert run(agent.turn(state['session_id'], request)) == result
    assert services.created == services.started == 1
    assert len(model.captured) == 0  # Validated approval executes without another model decision.


def test_prose_confirmation_does_not_authorize_side_effects(fixture):
    db, store, state, settings, services = fixture
    prepared, _ = prepare(fixture)
    model = scripted(('create_private_draft', {}), ('ask_user', {'question': 'Please confirm the summary.', 'field': 'details'}))
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(prepared, 'yes', 'yes, publish it')))
    assert services.created == services.started == 0
    tool_result = json.loads(model.captured[1][-1]['output'])
    assert 'Explicit confirmation' in tool_result['error']


def test_resume_across_instances_and_successful_job_becomes_review(fixture):
    db, store, state, settings, services = fixture
    prepared, _ = prepare(fixture)
    agent = Agent(store, settings, services, scripted(('create_private_draft', {}), ('start_listing_analysis', {})))
    result = run(agent.turn(state['session_id'], turn(prepared, 'confirm', 'confirm', confirmation_token=prepared['pending']['token'])))
    services.status = 'succeeded'
    async def no_model(*args):
        pytest.fail('Resuming completed analysis must not make another model call')
    fresh_db = Database(db.url)
    try:
        resumed = Agent(Store(fresh_db, 'owner-a'), settings, services, no_model)
        restored = run(resumed.public(resumed.store.load(state['session_id'])))
        assert restored['stage'] == 'review_ready'
        assert restored['listing']['estimated_value'] == 150
    finally:
        fresh_db.close()


def test_owner_and_revision_boundaries(fixture):
    db, store, state, settings, services = fixture
    with pytest.raises(HTTPException) as error:
        Store(db, 'other-owner').load(state['session_id'])
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        run(Agent(store, settings, services).turn(state['session_id'], Turn(request_id='x', expected_revision=0, message='hi')))
    assert error.value.status_code == 409
    stale = copy.deepcopy(state)
    store.save(state)
    with pytest.raises(HTTPException):
        store.save(stale)


def test_request_ids_cannot_be_reused_with_changed_message(fixture):
    db, store, state, settings, services = fixture
    agent = Agent(store, settings, services, scripted(('ask_user', {'question': 'What condition?', 'field': 'condition'})))
    run(agent.turn(state['session_id'], turn(state)))
    with pytest.raises(HTTPException) as error:
        run(agent.turn(state['session_id'], turn(state, message='different')))
    assert error.value.status_code == 409


def test_step_budget_and_provider_failure_preserve_progress(fixture):
    db, store, state, settings, services = fixture
    settings.listing_agent_max_steps = 2
    result = run(Agent(store, settings, services, scripted(('get_listing_context', {}), ('get_listing_context', {}))).turn(state['session_id'], turn(state)))
    assert result['pending']['field'] == 'condition'
    assert 'step limit' not in result['reply']
    async def broken(*args):
        raise httpx.ReadTimeout('provider timeout')
    result2 = run(Agent(store, settings, services, broken).turn(state['session_id'], turn(result, 'next')))
    assert 'could not finish' in result2['reply']
    assert len(result2['messages']) == 4
    assert services.created == 0


def test_claimed_upload_with_unchanged_photos_breaks_context_loop(fixture):
    db, store, state, settings, services = fixture
    state.update(facts={'category': 'shoes'}, evidence=dict(status='checked',
        missing_required=['shoe_sole'], missing_recommended=['size_or_material_label', 'condition_or_wear']))
    store.save(state)
    model = scripted(('assess_photo_evidence', {}), ('get_listing_context', {}), ('get_listing_context', {}))
    agent = Agent(store, settings, services, model)
    request = turn(state, message='I uploaded sole photo')
    result = run(agent.turn(state['session_id'], request))
    assert result['pending']['field'] == 'photos'
    assert 'Required before continuing: shoe sole (bottom)' in result['reply']
    assert 'Optional, not required to continue: size/material label, condition/wear' in result['reply']
    assert 'press “Use these photos”' in result['reply']
    assert '1 saved photos' in result['reply']
    assert services.assessed == services.created == services.started == 0
    assert run(agent.turn(state['session_id'], request)) == result
    assert len(model.captured) == 3


def test_step_budget_recovers_to_confirmation_without_skipping_human_approval(fixture):
    db, store, state, settings, services = fixture
    settings.listing_agent_max_steps = 1
    state.update(facts=dict(category='clothes', condition='New', size='M'),
                 evidence=dict(status='checked', missing_required=[], missing_recommended=['condition_or_wear']))
    store.save(state)
    result = run(Agent(store, settings, services, scripted(('get_listing_context', {}))).turn(state['session_id'], turn(state)))
    assert result['pending']['type'] == 'confirm_analysis'
    assert services.created == services.started == 0


def test_budget_recovery_after_confirmation_starts_exactly_one_job(fixture):
    db, store, state, settings, services = fixture
    prepared, _ = prepare(fixture)
    settings.listing_agent_max_steps = 1
    agent = Agent(store, settings, services, scripted(('create_private_draft', {})))
    request = turn(prepared, 'confirm-recovery', 'Confirm', confirmation_token=prepared['pending']['token'])
    result = run(agent.turn(state['session_id'], request))
    assert result['stage'] == 'analyzing'
    assert services.created == services.started == 1
    assert run(agent.turn(state['session_id'], request)) == result
    assert services.created == services.started == 1


def test_model_photo_question_separates_optional_from_required(fixture):
    db, store, state, settings, services = fixture
    state['evidence'] = dict(status='checked', missing_required=['shoe_sole'], missing_recommended=['condition_or_wear'])
    store.save(state)
    result = run(Agent(store, settings, services, scripted(('ask_user', dict(field='photos',
        question='You must provide sole and condition photos.')))).turn(state['session_id'], turn(state)))
    assert 'Optional, not required to continue: condition/wear.' in result['reply']
    assert 'You must provide' not in result['reply']


@pytest.mark.parametrize('field', ['photos', 'condition', 'details'])
def test_recommended_photos_never_become_a_blocking_question(fixture, field):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='shoes'), evidence=dict(status='checked', missing_required=[],
        missing_recommended=['size_or_material_label', 'condition_or_wear']))
    store.save(state)
    model = scripted(('ask_user', dict(field=field, question='Upload wear photos or tell me which recommended views are unavailable.')))
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state, message='Continue')))
    assert result['pending']['field'] == 'condition'
    assert 'unavailable' not in result['reply']
    assert services.created == 0


def test_recommended_photos_do_not_block_ready_summary(fixture):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='shoes', condition='New', size='US 8'),
        evidence=dict(status='checked', missing_required=[], missing_recommended=['condition_or_wear']))
    store.save(state)
    model = scripted(('ask_user', dict(field='photos', question='Upload optional wear photos.')))
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state)))
    assert result['pending']['type'] == 'confirm_analysis'
    assert services.created == services.started == 0


@pytest.mark.parametrize('field,message,value', [
    ('condition', 'New', 'New'), ('condition', 'new with tags', 'NewWithTags'),
    ('condition', 'LikeNew', 'LikeNew'), ('category', 'shoes', 'shoes'),
    ('size', 'US 8.5', 'US 8.5'), ('size', 'US 10', 'US 10'), ('size', 'M', 'M'),
])
def test_clear_answer_to_current_question_is_saved_without_model_quote(fixture, field, message, value):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='clothes' if value == 'M' else 'shoes', condition='New', size='US 8'),
                 evidence=dict(status='checked', missing_required=[]))
    state['facts'].pop(field)
    state['pending'] = dict(type='question', field=field, question='Provide ' + field, version=Agent.version(state))
    store.save(state)
    async def no_model(*args):
        pytest.fail('A clear answer must not need a model to quote it')
    agent = Agent(store, settings, services, no_model)
    request = turn(state, message=message)
    result = run(agent.turn(state['session_id'], request))
    assert result['facts'][field] == value
    assert result['pending']['type'] == 'confirm_analysis'
    assert store.load(state['session_id'])['fact_provenance'][field] == 'user_message'
    assert services.created == services.started == 0
    assert run(agent.turn(state['session_id'], request)) == result


def test_new_condition_answer_advances_to_size_not_same_question(fixture):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='shoes'), evidence=dict(status='checked', missing_required=[]))
    state['pending'] = dict(type='question', field='condition', question='What condition?', version=Agent.version(state))
    store.save(state)
    model = scripted()  # No provider call needed to accept this answer.
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state, message='New')))
    assert result['facts']['condition'] == 'New'
    assert result['pending']['field'] == 'size'
    assert 'Please select a valid size:' in result['reply']
    assert 'US 10' in result['reply']
    assert model.captured == []


@pytest.mark.parametrize('proposed,message', [('10', '10'), ('US 10', '10'), ('EU 43', 'EU 43'), ('US 10', 'US 10.5')])
def test_invalid_or_inferred_shoe_size_is_rejected(fixture, proposed, message):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='shoes', condition='New'), evidence=dict(status='checked', missing_required=[]))
    state['pending'] = dict(type='question', field='size', question='Select size', version=Agent.version(state))
    store.save(state)
    model = scripted(('record_user_facts', {'facts': {'size': proposed}, 'evidence_quote': message}),
                     ('ask_user', {'field': 'size', 'question': 'Size?'}))
    # US 10.5 itself is valid and handled directly, not converted to US 10.
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state, message=message)))
    if message == 'US 10.5':
        assert result['facts']['size'] == 'US 10.5'
    else:
        assert 'size' not in result['facts']
        assert 'error' in json.loads(model.captured[1][-1]['output'])
        assert result['pending']['field'] == 'size'
        assert 'US 10' in result['reply']
    assert services.created == services.started == 0


def test_old_invalid_size_cannot_be_confirmed_or_used_to_create_draft(fixture):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='shoes', condition='New', size='10'), evidence=dict(status='checked', missing_required=[]))
    state['approved'] = Agent.version(state)
    store.save(state)
    agent = Agent(store, settings, services, scripted(('prepare_analysis_confirmation', {}),
        ('create_private_draft', {}), ('ask_user', {'field': 'size', 'question': 'Choose size'})))
    result = run(agent.turn(state['session_id'], turn(state, message='Continue')))
    assert result['pending']['field'] == 'size'
    assert services.created == services.started == 0


def test_agent_size_options_match_web_category_lists():
    import re
    from pathlib import Path
    from app.listing_agent import SIZE_OPTIONS
    source = (Path(__file__).resolve().parents[1] / 'apps/web/src/App.jsx').read_text()
    def values(pattern):
        return re.findall(r"'([^']+)'", re.search(pattern, source).group(1))
    assert SIZE_OPTIONS['shoes'] == values(r"if \(category === 'shoes'\) return \[([^\]]+)\]")
    assert SIZE_OPTIONS['handbag'] == values(r"if \(category === 'handbag'\) return \[([^\]]+)\]")
    assert SIZE_OPTIONS['accessories'] == values(r'const ACCESSORY_SIZE_OPTIONS = \[([^\]]+)\]')
    assert SIZE_OPTIONS['clothes'] == values(r'const APPAREL_SIZE_OPTIONS = \[([^\]]+)\]') + values(r'const US_NUMERIC_APPAREL_SIZE_OPTIONS = \[([^\]]+)\]')


@pytest.mark.parametrize('message', ['new?', 'not new', 'New or Like new', 'I am not sure'])
def test_ambiguous_condition_is_not_directly_recorded(fixture, message):
    db, store, state, settings, services = fixture
    state['pending'] = dict(type='question', field='condition', question='What condition?', version=Agent.version(state))
    store.save(state)
    result = run(Agent(store, settings, services, scripted(('ask_user', dict(field='condition',
        question='Please clarify the condition.')))).turn(state['session_id'], turn(state, message=message)))
    assert 'condition' not in result['facts']


def test_missing_views_block_confirmation_and_waiver_needs_explicit_evidence(fixture):
    db, store, state, settings, services = fixture
    state.update(facts=dict(category='clothes', condition='New', size='M'),
                 evidence=dict(status='checked', missing_required=['brand_label']))
    store.save(state)
    model = scripted(('prepare_analysis_confirmation', {}),
        ('record_evidence_unavailable', {'role': 'brand_label', 'evidence_quote': 'hello'}),
        ('ask_user', {'question': 'Please add the label photo.', 'field': 'photos'}))
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state, message='hello')))
    assert not result['waivers']
    assert result['pending']['type'] == 'question'
    next_model = scripted(('record_evidence_unavailable', {'role': 'brand_label', 'evidence_quote': "I don't have the label"}), ('prepare_analysis_confirmation', {}))
    approved = run(Agent(store, settings, services, next_model).turn(state['session_id'], turn(result, 'waive', "I don't have the label")))
    assert approved['pending']['waived_views'] == ['brand_label']


def test_coverage_timeout_requires_category_but_does_not_skip_full_analysis(fixture):
    db, store, state, settings, services = fixture
    state.update(facts=dict(condition='New', size='M'), evidence=dict(status='timed_out', missing_required=[]))
    store.save(state)
    model = scripted(('prepare_analysis_confirmation', {}), ('ask_user', {'question': 'Which category?', 'field': 'category'}))
    result = run(Agent(store, settings, services, model).turn(state['session_id'], turn(state)))
    assert 'category' in json.loads(model.captured[1][-1]['output'])['error']
    assert result['pending']['field'] == 'category'
    after = scripted(('record_user_facts', {'facts': {'category': 'clothes'}, 'evidence_quote': 'clothes'}),
                     ('prepare_analysis_confirmation', {}))
    ready = run(Agent(store, settings, services, after).turn(state['session_id'], turn(result, 'category', 'clothes')))
    assert ready['pending']['type'] == 'confirm_analysis'
    assert ready['evidence']['status'] == 'timed_out'
    assert services.assessed == 0  # Selecting category does not retry timed-out coverage.


def test_publication_and_trade_tools_have_separate_confirmation_boundaries():
    schemas = tools()
    assert [t['name'] for t in schemas if 'publish' in t['name']] == ['publish_listing']
    assert {'prepare_trade_request', 'send_trade_request', 'cancel_trade_request'} <= {t['name'] for t in schemas}
    for tool in schemas:
        schema = tool['parameters']
        assert schema['additionalProperties'] is False
        assert set(schema['required']) == set(schema['properties'])
        assert '$ref' not in json.dumps(schema)


def test_model_cannot_publish_with_prose_or_analysis_approval(fixture):
    db, store, state, settings, services = fixture
    model = scripted(('publish_listing', {}), ('ask_user', {'field': 'details', 'question': 'Complete the private draft first.'}))
    run(Agent(store, settings, services, model).turn(state['session_id'], turn(state, message='yes publish it')))
    assert 'Explicit publication confirmation' in json.loads(model.captured[1][-1]['output'])['error']
    assert services.created == services.started == 0


def test_interrupted_old_turn_cannot_overwrite_a_newer_turn(fixture):
    db, store, state, settings, services = fixture
    old = turn(state, 'interrupted', 'New, M')
    assert store.request(state, old) == (None, False)
    store.save(state)  # Process stopped after its input checkpoint.
    newer = scripted(('record_user_facts', {'facts': {'condition': 'LikeNew'}, 'evidence_quote': 'Like new'}),
                     ('ask_user', {'question': 'What size?', 'field': 'size'}))
    updated = run(Agent(store, settings, services, newer).turn(state['session_id'], turn(state, 'newer', 'Like new')))
    with pytest.raises(HTTPException) as error:
        run(Agent(store, settings, services, newer).turn(state['session_id'], old))
    assert error.value.status_code == 409
    assert store.load(state['session_id'])['facts']['condition'] == 'LikeNew'


def test_interruption_after_reply_checkpoint_replays_without_another_model_call(fixture):
    db, store, state, settings, services = fixture
    model = scripted(('ask_user', {'question': 'What condition?', 'field': 'condition'}))
    agent = Agent(store, settings, services, model)
    request = turn(state)
    original_complete = store.complete
    store.complete = lambda *args: (_ for _ in ()).throw(RuntimeError('crash before request completion'))
    with pytest.raises(RuntimeError):
        run(agent.turn(state['session_id'], request))
    store.complete = original_complete
    replay = run(agent.turn(state['session_id'], request))
    assert replay['reply'] == 'What condition?'
    assert len(model.captured) == 1
    assert len(replay['messages']) == 2


def test_another_worker_cannot_enter_the_same_agent_session(fixture):
    db, store, state, settings, services = fixture
    other_db = Database(db.url)
    try:
        with store.lock(state['session_id']):
            with pytest.raises(HTTPException) as error:
                with Store(other_db, 'owner-a').lock(state['session_id']):
                    pytest.fail('Concurrent agent turn obtained the session lock')
            assert error.value.status_code == 409
    finally:
        other_db.close()
