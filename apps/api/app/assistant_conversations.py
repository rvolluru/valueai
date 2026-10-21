"""Inactive parent-conversation persistence foundation; no model or domain writes.

Use a dedicated Database connection per operation. A committed turn, transcript,
result sets and replay response are one transaction. This is not a tool ledger:
future side-effect execution must retain its own durable domain idempotency.
"""
import hashlib
import json
import uuid

from fastapi import HTTPException
from .db import utc_now_iso


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class ConversationStore:
    def __init__(self, db, owner):
        self.db, self.owner = db, owner

    def create(self, request_id):
        if not request_id or len(request_id) > 120:
            raise ValueError('A bounded creation request ID is required')
        key = str(uuid.uuid5(uuid.NAMESPACE_URL, encoded(['jouft-conversation', self.owner, request_id])))
        state = dict(messages=[], result_sets=[], focus=None, workflow_id=None, pending=None)
        p = self.db.param
        self.db.execute(f'INSERT INTO assistant_conversations VALUES ({p},{p},0,{p},{p},{p}) '
                        'ON CONFLICT (conversation_id) DO NOTHING',
                        (key, self.owner, encoded(state), utc_now_iso(), utc_now_iso()))
        self.db.commit()
        return self.load(key)

    def load(self, key):
        p = self.db.param
        row = self.db.fetchone(f'SELECT revision,state_json FROM assistant_conversations '
            f'WHERE conversation_id={p} AND owner_subject={p}', (key, self.owner))
        self.db.commit()
        if not row:
            raise HTTPException(404, 'Conversation not found')
        return dict(conversation_id=key, revision=row[0], **json.loads(row[1]))

    def replay(self, key, request_id, user_input):
        self.load(key)  # Never reveal even a cached response to another owner.
        p = self.db.param
        row = self.db.fetchone(f'SELECT input_hash,result_json FROM assistant_conversation_turns '
            f'WHERE conversation_id={p} AND request_id={p}', (key, request_id))
        self.db.commit()
        if not row:
            return None
        if row[0] != hashlib.sha256(encoded(user_input).encode()).hexdigest():
            raise HTTPException(409, 'Request ID already used with different input')
        return json.loads(row[1])

    def commit_turn(self, key, *, request_id, expected_revision, user_input, reply,
                    result_sets, focus=None, workflow_id=None, gallery=None, outcome=None, user_created_at=None):
        """Inputs beyond user_input must be server-produced, never client context."""
        if not request_id or len(request_id) > 120:
            raise ValueError('A bounded turn request ID is required')
        self.load(key)
        with self.db.analysis_execution_lock('assistant-conversation:' + key) as acquired:
            if not acquired:
                raise HTTPException(409, 'Another turn is running; retry the same request')
            previous = self.replay(key, request_id, user_input)
            if previous is not None:
                return previous
            state = self.load(key)
            if state['revision'] != expected_revision:
                raise HTTPException(409, 'Conversation changed; reload before continuing')
            if workflow_id:
                p = self.db.param
                owned = self.db.fetchone(f'SELECT session_id FROM listing_agent_sessions WHERE session_id={p} '
                    f'AND owner_subject={p}', (workflow_id, self.owner))
                self.db.commit()
                if not owned:
                    raise HTTPException(404, 'Listing workflow not found')
            fields = dict(messages=[*state['messages'], dict(role='user', content=user_input, request_id=request_id, created_at=user_created_at or utc_now_iso()),
                                     dict(role='assistant', content=reply, request_id=request_id, created_at=utc_now_iso(), result_sets=result_sets)][-40:],
                          result_sets=result_sets, focus=focus, workflow_id=workflow_id, pending=None)
            first = next((m['content'] for m in state['messages'] if m['role'] == 'user'), user_input)
            title = first.get('message', '') if isinstance(first, dict) else str(first)
            fields['title'] = state.get('title') or title[:80] or 'New chat'
            if outcome is not None:
                from .assistant_capabilities import ReadOutcome
                fields['outcome'] = ReadOutcome.model_validate(outcome).model_dump()
            result = dict(conversation_id=key, revision=expected_revision + 1, **fields)
            if gallery:
                result['gallery'] = dict(request_id=request_id, listing=gallery)
            p = self.db.param
            try:
                row = self.db.fetchone(f'UPDATE assistant_conversations SET state_json={p}, revision=revision+1, '
                    f'updated_at={p} WHERE conversation_id={p} AND owner_subject={p} AND revision={p} RETURNING revision',
                    (encoded(fields), utc_now_iso(), key, self.owner, expected_revision))
                if not row:
                    raise HTTPException(409, 'Conversation changed; reload before continuing')
                self.db.execute(f'INSERT INTO assistant_conversation_turns VALUES ({p},{p},{p},{p},{p})',
                    (key, request_id, hashlib.sha256(encoded(user_input).encode()).hexdigest(), encoded(result), utc_now_iso()))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return result
