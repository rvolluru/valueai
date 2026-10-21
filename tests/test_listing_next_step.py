import asyncio
import copy
from app.listing_agent import Agent, Turn, listing_next_step
from test_listing_agent import fixture, scripted


def test_remaining_details_are_specific_and_read_only():
    state = dict(stage='collecting', facts={'category': 'clothes'}, photos=[{'image_id': 'one'}],
        evidence={'status': 'checked', 'missing_required': [], 'missing_recommended': ['full_back']}, waivers=[])
    original = copy.deepcopy(state)
    result = listing_next_step(state)
    assert result['missing_fields'] == ['condition', 'size']
    assert result['field'] == 'condition'
    assert 'condition, size' in result['reply']
    assert result['reply'].endswith('What is the condition: New with tags, New, or Like new?')
    assert state == original
    state['facts']['condition'] = 'New'
    assert listing_next_step(state)['field'] == 'size'
    state['facts']['size'] = 'M'
    assert listing_next_step(state)['field'] is None
    assert 'Confirm the summary' in listing_next_step(state)['reply']


def test_required_evidence_precedes_facts_but_optional_views_do_not_block():
    state = dict(stage='collecting', facts={'category': 'shoes'}, photos=[{}], waivers=[],
        evidence={'status': 'checked', 'missing_required': ['shoe_sole']})
    assert listing_next_step(state)['field'] == 'photos'
    assert 'shoe sole' in listing_next_step(state)['reply']
    state['waivers'] = ['shoe_sole']
    assert listing_next_step(state)['field'] == 'condition'
    state['stage'] = 'published'
    assert listing_next_step(state)['missing_fields'] == []
    assert 'published' in listing_next_step(state)['reply']


def test_pausing_on_status_after_coverage_recovers_concrete_intake_question(fixture):
    db, store, state, settings, services = fixture
    agent = Agent(store, settings, services, scripted(('assess_photo_evidence', {}), ('get_analysis_status', {})))
    result = asyncio.run(agent.turn(state['session_id'], Turn(request_id='upload-followup',
        expected_revision=state['revision'], message='I uploaded photos')))
    assert result['pending']['field'] == 'condition'
    assert result['reply'] == 'What is the condition: New with tags, New, or Like new?'
    assert result['next_step']['missing_fields'] == ['condition', 'size']
    assert services.assessed == 1
    assert services.created == services.started == 0
