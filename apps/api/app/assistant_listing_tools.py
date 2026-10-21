"""Parent adapters reuse child validation/ledger; approval tokens never enter model arguments."""
from pydantic import Field
from .listing_agent import Turn, ToolArgs, TOOL_MODELS, tools

# Final approvals are client actions, never model-selectable tools.
DIRECT_TOOLS = frozenset({
    'get_listing_context', 'assess_photo_evidence', 'record_user_facts',
    'record_evidence_unavailable', 'prepare_analysis_confirmation',
    'create_private_draft', 'start_listing_analysis', 'get_analysis_status',
    'prepare_draft_review', 'propose_listing_changes', 'discard_listing_changes',
    'keep_as_draft', 'find_marketplace_matches', 'prepare_trade_request', 'cancel_trade_request',
})


class RemoveEvidence(ToolArgs):
    image_id: str = Field(min_length=1, max_length=120)


DIRECT_TOOLS = DIRECT_TOOLS | {'remove_listing_photo'}


class AdapterTurn(Turn):
    # Included in the existing child request fingerprint, including on retries.
    tool_name: str
    tool_arguments: dict = Field(default_factory=dict)


def catalog():
    return [tool for tool in tools() if tool['name'] in DIRECT_TOOLS] + [dict(
        type='function', name='remove_listing_photo', strict=True,
        description='Remove one saved photo only on an explicit user removal request. Use an image_id from get_listing_context; never invent it. Preserves the other photos. Existing review photo changes are staged.',
        parameters=dict(type='object', additionalProperties=False, required=['image_id'],
            properties=dict(image_id=dict(type='string'))))]


def validate(name, arguments):
    if name not in DIRECT_TOOLS:
        raise ValueError('This listing operation requires a separate confirmation control')
    return (RemoveEvidence if name == 'remove_listing_photo' else TOOL_MODELS[name]).model_validate(arguments).model_dump()


async def execute(session_id, name, arguments, *, request_id, message, settings, principal, tasks):
    from .listing_agent_routes import agent_for
    arguments = validate(name, arguments)
    db, agent = agent_for(settings, principal, tasks)
    try:
        state = agent.store.load(session_id)  # Owner-scoped, never model-selected.
        if name == 'remove_listing_photo':
            import re
            from fastapi import HTTPException
            if not re.search(r'\b(remove|delete|discard)\b', message, re.I):
                raise HTTPException(409, 'Explicitly request removal of a saved photo first')
            from .listing_agent_routes import remove_photo, RemovePhoto
            return await remove_photo(session_id, RemovePhoto(request_id=request_id,
                expected_revision=state['revision'], **arguments), tasks, settings, principal)
        if name in {'get_listing_context', 'get_analysis_status'}:
            with agent.store.lock(session_id):
                result = await agent.public(agent.store.load(session_id))
            result['reply'] = (result['next_step']['reply'] if name == 'get_listing_context' else
                f"Listing stage: {result['stage']}. Analysis status: {(result.get('job') or {}).get('status', 'not started')}.")
            return result
        return await agent.turn(session_id, AdapterTurn(request_id=request_id,
            expected_revision=state['revision'], message=message,
            tool_name=name, tool_arguments=arguments))
    finally:
        db.close()
