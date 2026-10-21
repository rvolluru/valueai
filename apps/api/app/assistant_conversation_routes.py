"""Default-off explicit read-action API. Natural-language tool selection follows later."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field
from .auth import AuthPrincipal, get_request_principal
from .deps import get_settings
from .db import Database
from .settings import Settings
from .assistant_conversations import ConversationStore
from .assistant_reads import saved_listing, search_marketplace, MatchRead, grouped_matches, matching_preferences, trade_status
from .assistant_capabilities import ReadArguments, outcome

router = APIRouter(prefix='/v1/assistant-conversations', tags=['assistant-conversations'])


def enabled(settings: Settings = Depends(get_settings)):
    if not settings.assistant_conversations_enabled:
        raise HTTPException(404, 'Conversation pilot is not enabled')
    return settings


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=1, max_length=120)


class ReadTurn(Start, ReadArguments):
    expected_revision: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=2000)


class ResultSet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    domain: Literal['closet', 'marketplace', 'trades', 'shipping']
    source_listing_id: str | None = None
    source_title: str | None = None
    count: int = Field(ge=0)
    items: list[dict] = Field(max_length=12)
    offset: int = Field(default=0, ge=0)
    next_offset: int | None = Field(default=None, ge=0)
    query: ReadArguments | None = None


def connection(settings):
    return Database(settings.database_url)


@router.post('')
def create(payload: Start, settings: Settings = Depends(enabled), principal: AuthPrincipal = Depends(get_request_principal)):
    db = connection(settings)
    try:
        return ConversationStore(db, principal.subject).create(payload.request_id)
    finally:
        db.close()


@router.get('/{conversation_id}')
def load(conversation_id: str, settings: Settings = Depends(enabled), principal: AuthPrincipal = Depends(get_request_principal)):
    db = connection(settings)
    try:
        return ConversationStore(db, principal.subject).load(conversation_id)
    finally:
        db.close()


@router.get('')
def list_threads(settings: Settings = Depends(enabled), principal: AuthPrincipal = Depends(get_request_principal)):
    import json
    db = connection(settings)
    try:
        rows = db.fetchall(f'SELECT conversation_id,state_json,updated_at FROM assistant_conversations '
            f'WHERE owner_subject={db.param} ORDER BY updated_at DESC, conversation_id LIMIT 50', (principal.subject,))
        items = []
        for key, raw, updated in rows:
            state = json.loads(raw)
            first = next((m['content'] for m in state['messages'] if m['role'] == 'user'), '')
            title = first.get('message', '') if isinstance(first, dict) else first
            items.append(dict(conversation_id=key, title=state.get('title') or title[:80] or 'New chat', updated_at=updated))
        return dict(items=items)
    finally:
        db.close()


@router.post('/{conversation_id}/turns')
def read_turn(conversation_id: str, payload: ReadTurn, settings: Settings = Depends(enabled),
              principal: AuthPrincipal = Depends(get_request_principal)):
    return execute_read(conversation_id, payload, settings, principal)


def execute_read(conversation_id, payload, settings, principal, *, preview=False):
    from .main import _app_assistant_listing_card, list_closet_listing_marketplace_matches
    from .assistant_context import listing_detail_summary
    db = connection(settings)
    try:
        store = ConversationStore(db, principal.subject)
        user_input = payload.model_dump(exclude={'expected_revision', 'request_id'})
        # Keep pre-extension read replay hashes compatible when new fields are unused.
        for optional in ('result_set_id', 'offer_id'):
            if user_input.get(optional) is None:
                user_input.pop(optional, None)
        cached = None if preview else store.replay(conversation_id, payload.request_id, user_input)
        if cached is not None:
            return cached
        state = store.load(conversation_id)
        if state['revision'] != payload.expected_revision:
            raise HTTPException(409, 'Conversation changed; reload before continuing')
        offset = 0
        if payload.action == 'more':
            previous = next((group for group in state['result_sets'] if group['id'] == payload.result_set_id), None)
            if not previous or previous.get('next_offset') is None or not previous.get('query'):
                raise HTTPException(409, 'These results cannot be paged. Refresh the original query first.')
            offset = previous['next_offset']
            if not isinstance(offset, int) or not 0 < offset <= 5000:
                raise HTTPException(409, 'Refresh the original query first.')
            payload = ReadTurn(**previous['query'], request_id=payload.request_id,
                expected_revision=payload.expected_revision, message=payload.message)
            if payload.action not in {'closet', 'lookup', 'search', 'matches', 'trades', 'pending_trades', 'shipping'}:
                raise HTTPException(409, 'These results do not support paging.')
        groups = []
        focus = None
        gallery = None
        status = 'available'
        actions = [dict(action='closet', label='Choose another listing')]
        if payload.action == 'preferences':
            prefs = matching_preferences(subject=principal.subject, db=db)
            labels = {'category_preferences': 'Categories', 'tops_size': 'Tops size', 'dresses_size': 'Dresses size', 'bottoms_size': 'Bottoms size', 'shoes_size': 'Shoes size'}
            lines = [f"{labels[key]}: {', '.join(map(str, value)) if isinstance(value, list) else value or 'Not set'}" for key, value in prefs.items()]
            reply = 'Your saved matching preferences:\n\n' + '\n'.join(lines) + '\n\nThese are read-only here. Jouft’s matching rules are unchanged.'
            status = 'available' if any(prefs.values()) else 'empty'
        elif payload.action in {'trades', 'pending_trades', 'shipping'}:
            rows = trade_status(subject=principal.subject, db=db, offer_id=payload.offer_id,
                shipping=payload.action == 'shipping', pending_only=payload.action == 'pending_trades')
            page = rows[offset:offset + 12]
            groups = [dict(domain='trades' if payload.action == 'pending_trades' else payload.action, count=len(rows), items=page,
                           next_offset=offset + len(page) if offset + len(page) < len(rows) else None)]
            reply = ('Here are your saved trade statuses (up to 50 recent offers).' if payload.action == 'trades'
                     else 'Here are saved shipment statuses for your trades. This does not refresh carrier tracking.') if rows else (
                        'You have no recent trade offers.' if payload.action == 'trades' else 'No saved shipments were found for your recent trades.')
            status = 'more_available' if groups[0]['next_offset'] is not None else 'available' if rows else 'empty'
            if payload.action == 'pending_trades':
                reply = 'Here are your pending trade offers (among up to 50 recent offers).' if rows else 'No pending trades were found among your 50 most recent offers.'
            if payload.action == 'trades' and payload.offer_id:
                actions.insert(0, dict(action='shipping', offer_id=payload.offer_id, label='Show shipment status'))
        elif payload.action in {'details', 'photos'}:
            target_id = payload.listing_id or (state['focus'] if payload.action == 'photos' else None)
            if not target_id:
                raise HTTPException(422, 'Choose a listing for details')
            item = saved_listing(target_id, subject=principal.subject, db=db)
            focus = target_id
            if payload.action == 'photos':
                gallery = _app_assistant_listing_card(item, settings)
                if not gallery['images']:
                    gallery = None
                reply = 'Opening the image gallery.' if gallery else 'This item has no available photos.'
                status = 'available' if gallery else 'no_photos'
            else:
                reply = listing_detail_summary(item)
                if _app_assistant_listing_card(item, settings)['images']:
                    actions.insert(0, dict(action='photos', listing_id=target_id, label='View photos'))
            groups = [dict(domain='closet' if item['owner_subject'] == principal.subject else 'marketplace',
                           count=1, items=[item])]
        elif payload.action == 'lookup':
            owned = db.list_owner_listings(principal.subject, limit=5000)
            found = search_marketplace(owned, payload.terms, offset=offset)
            groups = [dict(domain='closet', **found)]
            if found['count'] == 1 and found['items']:
                item = saved_listing(found['items'][0]['listing_id'], subject=principal.subject, db=db)
                focus = item['listing_id']
                reply = listing_detail_summary(item)
                actions = [dict(action='photos', listing_id=focus, label='View photos')] if _app_assistant_listing_card(item, settings)['images'] else []
            elif found['count']:
                status = 'clarification'
                reply = f"I found {found['count']} closet listings matching that description. Which one do you mean? Choose a title or number below."
                actions = [dict(action='details', listing_id=item['listing_id'], label=f"View {item.get('title') or 'listing'}"[:100]) for item in found['items'][:3]]
            else:
                status = 'empty'
                reply = 'I couldn’t find a closet listing matching that description. Try a different brand, title, category or size.'
        elif payload.action == 'closet':
            items = db.list_owner_listings(principal.subject, limit=5000)
            page = items[offset:offset + 12]
            groups = [dict(domain='closet', count=len(items), items=page,
                           next_offset=offset + len(page) if offset + len(page) < len(items) else None)]
            reply = 'Here are your recent closet items.'
            if not items:
                status, reply = 'empty', 'Your closet is empty.'
            elif len(items) > 12:
                status = 'more_available'
        elif payload.action == 'search':
            items = db.list_recent_listings(limit=5000, include_analysis=False, include_media=True, active_only=True)
            items = [item for item in items if item.get('owner_subject') != principal.subject]
            found = search_marketplace(items, payload.terms, offset=offset)
            groups = [dict(domain='marketplace', **found)]
            reply = f"Found {found['count']} Marketplace items."
            reply += ' These are browsing results, not confirmed trade matches.'
            status = 'more_available' if found['next_offset'] is not None else 'available' if found['count'] else 'empty'
        else:
            owned = db.list_owner_listings(principal.subject, limit=100)
            eligible = [item for item in owned if (not payload.listing_id or item['listing_id'] == payload.listing_id)
                and str(item.get('status') or '').lower() == 'active' and float(item.get('estimated_value') or 0) > 0]
            groups = grouped_matches(MatchRead(scope='one' if payload.listing_id else 'all_eligible',
                source_listing_id=payload.listing_id),
                owned_listings=owned,
                read_source=lambda key, limit: list_closet_listing_marketplace_matches(key, limit=limit,
                    offset=offset, principal=principal, db=db, settings=settings))
            reply = 'Here are current matches grouped by your items.'
            count = sum(group['count'] for group in groups)
            if not eligible:
                status, reply = 'ineligible', 'A published listing with a saved positive value is required to check matches. This selection has no eligible source listing.'
            elif not count:
                status, reply = 'no_matches', 'No eligible Marketplace matches are available for this selection right now. Matching criteria are fixed by Jouft and cannot be broadened.'
            elif any(group.get('has_more') for group in groups):
                status = 'more_available'
                reply += ' More matches exist than are displayed; this chat shows up to 3 per item.'
            if eligible:
                actions.insert(0, dict(action='matches', listing_id=payload.listing_id, label='Refresh matches'))
            groups = [dict(domain='marketplace', source_listing_id=g['source_listing_id'], source_title=g['source_title'],
                           count=g['count'], items=g['items'], next_offset=g.get('next_offset')) for g in groups]
        result_sets = [ResultSet(id=f'{payload.request_id}:{index}',
            **{**group, 'offset': offset, 'query': ReadArguments(action=payload.action,
                listing_id=group.get('source_listing_id') if payload.action == 'matches' else payload.listing_id,
                offer_id=payload.offer_id, terms=payload.terms).model_dump(),
               'items': group['items'] if group['domain'] in {'trades', 'shipping'} else [_app_assistant_listing_card(item, settings) for item in group['items']]}).model_dump()
            for index, group in enumerate(groups)]
        for group in result_sets:
            if group['next_offset'] is not None:
                label = f"More matches for {group['source_title']}" if group.get('source_title') else 'Show more results'
                actions.append(dict(action='more', result_set_id=group['id'], label=label[:100]))
        if offset and not any(group['items'] for group in result_sets):
            reply = 'There are no more results on this page. Inventory may have changed; refresh the original query to start again.'
            status = 'empty'
            actions.insert(0, dict(**ReadArguments(action=payload.action, listing_id=payload.listing_id,
                offer_id=payload.offer_id, terms=payload.terms).model_dump(), label='Refresh results'))
        presentation = outcome(status, actions)
        if preview:
            return dict(reply=reply, result_sets=result_sets, focus=focus, gallery=gallery, outcome=presentation)
        return store.commit_turn(conversation_id, request_id=payload.request_id,
            expected_revision=payload.expected_revision, user_input=user_input, reply=reply,
            result_sets=result_sets, focus=focus, workflow_id=state['workflow_id'], gallery=gallery, outcome=presentation)
    finally:
        db.close()


class MessageTurn(Start):
    expected_revision: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=2000)


@router.post('/{conversation_id}/messages')
async def message_turn(conversation_id: str, payload: MessageTurn, tasks: BackgroundTasks, settings: Settings = Depends(enabled),
                       principal: AuthPrincipal = Depends(get_request_principal)):
    from .assistant_read_agent import run
    from .db import utc_now_iso
    received_at = utc_now_iso()
    db = connection(settings)
    try:
        store = ConversationStore(db, principal.subject)
        user_input = dict(message=payload.message, mode='model_read')
        cached = store.replay(conversation_id, payload.request_id, user_input)
        if cached is not None:
            return cached
        state = store.load(conversation_id)
        if state['revision'] != payload.expected_revision:
            raise HTTPException(409, 'Conversation changed; reload before continuing')
        async def read(arguments):
            request = ReadTurn(**arguments, request_id=payload.request_id,
                expected_revision=payload.expected_revision, message=payload.message)
            return execute_read(conversation_id, request, settings, principal, preview=True)
        if settings.listing_agent_enabled and state.get('workflow_id'):
            from .listing_agent import Store as ChildStore
            child_state = ChildStore(db, principal.subject).load(state['workflow_id'])
            state['workflow_context'] = {key: child_state.get(key) for key in ('listing_id', 'stage', 'job_id', 'facts', 'photos', 'evidence')}
        async def workflow(args):
            from .listing_agent_routes import start, open_review, get_session, Start as ChildStart, ReviewListing
            import uuid
            request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'parent:{conversation_id}:{payload.request_id}'))
            if args.mode == 'start':
                child = await start(ChildStart(request_id=request_id), tasks, settings, principal)
            elif args.listing_id:
                child = await open_review(ReviewListing(request_id=request_id, listing_id=args.listing_id), tasks, settings, principal)
            elif state.get('workflow_id'):
                child = await get_session(state['workflow_id'], tasks, settings, principal)
            else:
                return dict(result_sets=[], focus=None, reply='This thread has no listing workflow yet. Ask me to create a new listing or name a private listing to review.', outcome=outcome_fn('clarification'))
            return dict(result_sets=[], focus=None, workflow_id=child['session_id'],
                reply='Add photos to begin your new listing. Nothing is published without your confirmation.' if args.mode == 'start'
                    else 'Your saved listing workflow is ready to continue.', outcome=outcome_fn('available'))
        from .assistant_capabilities import outcome as outcome_fn
        async def listing(name, arguments):
            from .assistant_listing_tools import execute
            import uuid
            child_request = str(uuid.uuid5(uuid.NAMESPACE_URL, f'parent-action:{conversation_id}:{payload.request_id}'))
            try:
                child = await execute(state['workflow_id'], name, arguments, request_id=child_request,
                    message=payload.message, settings=settings, principal=principal, tasks=tasks)
            except HTTPException as error:
                if (error.headers or {}).get('X-Assistant-Outcome') != 'blocked':
                    raise
                return dict(result_sets=[], focus=None, workflow_id=state['workflow_id'],
                    reply=str(error.detail), outcome=outcome_fn('blocked'))
            return dict(result_sets=[], focus=None, workflow_id=child['session_id'],
                reply=child.get('reply', 'Photo removed. Other saved photos are preserved. Recheck coverage before continuing.'),
                workflow_context={key: child.get(key) for key in ('listing_id', 'stage', 'job_id', 'facts', 'photos', 'evidence')},
                outcome=outcome_fn('available'))
        outcome = await run(settings, state, payload.message, read,
            workflow=workflow if settings.listing_agent_enabled else None,
            listing=listing if settings.listing_agent_enabled else None)
        return store.commit_turn(conversation_id, request_id=payload.request_id,
            expected_revision=payload.expected_revision, user_input=user_input, reply=outcome['reply'],
            result_sets=outcome['result_sets'], focus=outcome['focus'], workflow_id=outcome.get('workflow_id', state['workflow_id']), gallery=outcome.get('gallery'), outcome=outcome.get('outcome'), user_created_at=received_at)
    finally:
        db.close()
