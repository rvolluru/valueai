"""Bounded presentation history. Never copy approval tokens into timeline events."""
import copy
import hashlib
import json
from .db import utc_now_iso


def capture(state, actual=None):
    events = state.setdefault('timeline_events', [])
    signatures = state.setdefault('timeline_signatures', {})
    legacy = not state.get('timeline_initialized') and bool(state.get('messages'))
    changed = False

    def record(kind, snapshot):
        nonlocal changed
        signature = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        if signatures.get(kind) == signature:
            return
        first = kind not in signatures
        signatures[kind] = signature
        if snapshot is None:
            return
        when = utc_now_iso()
        inferred = False
        # Legacy histories have no event clock. Use a real message anchor only;
        # never invent a historical timestamp or label it precisely observed.
        if first and legacy:
            candidates = [m for m in state.get('messages', []) if m.get('created_at')]
            if candidates:
                anchor = next((m for m in reversed(candidates) if kind != 'actions' and 'uploaded these original photos' in str(m.get('content', ''))), candidates[-1])
                when, inferred = anchor['created_at'], True
        events.append(dict(id=f'{kind}-{state.get("revision", 0)}-{signature[:12]}', kind=kind,
            created_at=when, inferred_time=inferred, snapshot=copy.deepcopy(snapshot)))
        state['timeline_events'] = events[-80:]
        changed = True

    photos = [{k: p.get(k) for k in ('image_id', 'url')} for p in state.get('photos', [])]
    record('photos', dict(photos=photos) if photos or any(e['kind'] == 'photos' for e in events) else None)
    evidence = state.get('evidence')
    record('coverage', dict(photos=photos, evidence=evidence, waivers=state.get('waivers', []))
           if evidence or any(e['kind'] == 'coverage' for e in events) else None)
    if actual is not None:
        listing = actual.get('listing') or {}
        pending = state.get('pending') or {}
        # Select safe fields explicitly. A historical card is never an approval.
        snapshot = dict(stage=state['stage'], facts=state.get('facts', {}),
            pending_type=pending.get('type'),
            listing={k: listing.get(k) for k in ('listing_id', 'title', 'brand', 'category', 'condition', 'size', 'description', 'estimated_value', 'status')},
            changes=(state.get('edit_proposal') or {}).get('changes'),
            trade={k: {field: item.get(field) for field in ('listing_id', 'title', 'brand', 'size', 'condition', 'estimated_value')}
                   if (item := (state.get('trade_proposal') or {}).get(k)) else None for k in ('offered', 'target')})
        matches = actual.get('marketplace_matches')
        if matches is not None:
            snapshot['matches'] = dict(count=matches.get('count', 0), items=[
                {k: item.get(k) for k in ('listing_id', 'title', 'brand', 'size', 'condition', 'estimated_value', 'image')}
                for item in matches.get('items', [])[:12]])
        if state.get('sent_trade'):
            snapshot['sent_trade'] = {k: state['sent_trade'].get(k) for k in ('offer_id', 'status')}
        record('actions', snapshot if (listing or pending.get('type') == 'confirm_analysis' or state.get('edit_proposal') or state.get('trade_proposal')) else None)
    state['timeline_initialized'] = True
    return changed
