import json
from app.listing_timeline import capture


def test_timeline_snapshots_are_durable_deduplicated_and_exclude_approvals():
    state = dict(revision=0, stage='collecting', photos=[], facts={}, messages=[])
    assert not capture(state)
    state['photos'] = [{'image_id': 'one', 'url': '/one', 'content_hash': 'not-for-display'}]
    assert capture(state)
    state['evidence'] = {'status': 'checked', 'missing_required': []}
    assert capture(state)
    assert not capture(state)
    state['facts'] = {'size': '10', 'category': 'clothes'}
    state['pending'] = {'type': 'confirm_analysis', 'token': 'secret-approval'}
    assert capture(state, {})
    assert [e['kind'] for e in state['timeline_events']] == ['photos', 'coverage', 'actions']
    assert 'secret-approval' not in json.dumps(state['timeline_events'])
    assert 'not-for-display' not in json.dumps(state['timeline_events'])
    assert not capture(state, {})
    assert all(e['created_at'] for e in state['timeline_events'])
    state['facts']['size'] = '12'
    assert state['timeline_events'][-1]['snapshot']['facts']['size'] == '10'


def test_coverage_history_survives_photo_changes_without_claiming_current_success():
    state = dict(revision=0, stage='collecting', photos=[{'image_id': 'one', 'url': '/one'}],
        evidence={'status': 'checked', 'missing_required': []})
    capture(state)
    state.update(photos=[], evidence=None)
    capture(state)
    assert [e['kind'] for e in state['timeline_events']] == ['photos', 'coverage', 'photos', 'coverage']
    assert state['timeline_events'][1]['snapshot']['evidence']['status'] == 'checked'
    assert state['timeline_events'][-1]['snapshot']['evidence'] is None
    assert not capture(state)
