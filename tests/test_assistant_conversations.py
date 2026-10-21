import pytest
from fastapi import HTTPException
from app.db import Database
from app.assistant_conversations import ConversationStore


@pytest.fixture
def stores(tmp_path):
    db = Database(f'sqlite:///{tmp_path / "conversations.db"}')
    db.initialize()
    return db, ConversationStore(db, 'one'), ConversationStore(db, 'two')


def turn(store, key, **overrides):
    args = dict(request_id='turn', expected_revision=0, user_input='Find matches', reply='Here they are',
        result_sets=[dict(id='results', entries=[dict(source_id='a', target_id='b'), dict(source_id='c', target_id='b')])])
    return store.commit_turn(key, **{**args, **overrides})


def test_owner_creation_replay_and_restart(stores):
    db, first, other = stores
    state = first.create('create')
    key = state['conversation_id']
    assert first.create('create') == state
    assert other.create('create')['conversation_id'] != key
    result = turn(first, key)
    assert turn(first, key) == result  # Lost-response retry despite old revision.
    fresh = Database(db.url)
    resumed = ConversationStore(fresh, 'one')
    assert resumed.load(key) == result
    assert len(result['messages']) == 2
    assert len(result['result_sets'][0]['entries']) == 2
    with pytest.raises(HTTPException) as error: turn(other, key)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException): first.replay(key, 'turn', 'Different message')
    with pytest.raises(HTTPException): turn(first, key, request_id='second')
    assert resumed.load(key) == result


def test_turn_response_and_transcript_are_atomic(stores, monkeypatch):
    db, store, _ = stores
    state = store.create('create')
    original = db.execute
    def fail(sql, params=()):
        if 'INSERT INTO assistant_conversation_turns' in sql:
            raise RuntimeError('simulated interruption')
        return original(sql, params)
    monkeypatch.setattr(db, 'execute', fail)
    with pytest.raises(RuntimeError): turn(store, state['conversation_id'])
    assert store.load(state['conversation_id']) == state
    monkeypatch.setattr(db, 'execute', original)
    assert turn(store, state['conversation_id'])['revision'] == 1


def test_workflow_link_checks_owner(stores):
    from app.listing_agent import Store
    db, parent, _ = stores
    key = parent.create('create')['conversation_id']
    foreign = Store(db, 'two').create('child')['session_id']
    with pytest.raises(HTTPException): turn(parent, key, workflow_id=foreign)
    own = Store(db, 'one').create('child')['session_id']
    assert turn(parent, key, workflow_id=own)['workflow_id'] == own
