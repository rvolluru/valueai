"""Authoritative capabilities and presentation contracts for the read-only pilot.

The catalog describes executable adapters, not desired future functionality.
Business policies remain in the normal domain services.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ReadAction = Literal['closet', 'lookup', 'search', 'details', 'photos', 'matches', 'more', 'preferences', 'trades', 'pending_trades', 'shipping']
CAPABILITIES = {
    'closet': 'List recent owned items. No editing, creation or publication.',
    'lookup': 'Resolve an owned listing by brand/title/category/size terms before asking the user to choose. '
              'Example Chanel shoes uses terms [Chanel, shoes]. One result returns saved details; '
              'several results return only matching choices. Do not ask users to browse their whole closet first.',
    'search': 'Keyword browse of public Active Marketplace items using brand/title/category/condition/size. '
              'This is not trade matching and does not establish eligibility. No price-range filter exists.',
    'details': 'Read saved fields for an owned or public Active item. No reanalysis or valuation changes.',
    'photos': 'Open the authorized saved image gallery. Null listing_id uses unambiguous current focus. No image generation.',
    'matches': 'Read eligible Marketplace matches for one owned source ID or all eligible owned items with null ID. '
               'Matching rules are fixed by the backend: values, preferences, sizes, availability and sent-offer exclusions. '
               'Never relax, broaden, override or invent matching criteria. Search results are not qualified matches.',
    'more': 'Read the next page of a displayed result set using its exact result_set_id. The server preserves its query and matching rules. Never invent offsets.',
    'preferences': 'Read saved category and size matching preferences only. No profile changes or personal/contact/billing information.',
    'trades': 'Read all statuses among up to 50 recent trade offers for the current participant, or one authorized offer_id. Use pending_trades when the user asks for pending offers only. No send/accept/decline actions.',
    'pending_trades': 'Read only offers with pending status among the current participant’s 50 most recent trade offers. Use for pending trades/requests. Excludes accepted, declined, proposed and completed offers. No trade mutations.',
    'shipping': 'Read saved shipment carrier, tracking status and ETA for authorized trades (up to 50 recent offers) or one offer_id. No live carrier refresh, address disclosure, label purchase or payment.',
}


class ReadArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: ReadAction
    listing_id: str | None = Field(default=None, max_length=120)
    terms: list[str] = Field(default_factory=list, max_length=10)
    result_set_id: str | None = Field(default=None, max_length=160)
    offer_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode='after')
    def supported_arguments(self):
        if self.action not in {'search', 'lookup'} and self.terms:
            raise ValueError('Only keyword search accepts terms; matching criteria cannot be changed')
        if self.action in {'closet', 'search', 'lookup'} and self.listing_id:
            raise ValueError('This read does not accept a source listing')
        if self.action in {'more', 'preferences', 'trades', 'pending_trades', 'shipping'} and self.listing_id:
            raise ValueError('Use the appropriate result-set or offer reference, not a listing ID')
        if (self.action == 'more') != bool(self.result_set_id):
            raise ValueError('Only more-results requests require a result-set ID')
        if self.offer_id and self.action not in {'trades', 'shipping'}:
            raise ValueError('Offer references are only for trade/shipping status')
        if any(len(term) > 120 for term in self.terms):
            raise ValueError('Search terms are too long')
        return self


class NextAction(ReadArguments):
    label: str = Field(max_length=100)


class ReadOutcome(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['available', 'empty', 'no_matches', 'ineligible', 'more_available',
                    'no_photos', 'unavailable', 'clarification', 'unsupported', 'invalid_arguments', 'blocked', 'tool_failure']
    category: Literal['result', 'unclear', 'unsupported', 'blocked', 'tool_failure'] = 'result'
    retryable: bool = False
    next_actions: list[NextAction] = Field(default_factory=list, max_length=16)
    rules_fixed: bool = True

    @model_validator(mode='after')
    def classify(self):
        self.category = ('unclear' if self.status in {'clarification', 'invalid_arguments'} else
                         'unsupported' if self.status == 'unsupported' else
                         'blocked' if self.status in {'ineligible', 'unavailable', 'blocked'} else
                         'tool_failure' if self.status == 'tool_failure' else 'result')
        self.retryable = self.category == 'tool_failure'
        return self


class WorkflowArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['start', 'resume']
    listing_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode='after')
    def new_is_not_review(self):
        if self.mode == 'start' and self.listing_id:
            raise ValueError('A new draft must not reuse an existing listing')
        return self


def tool_catalog(workflows=False):
    tools = [dict(type='function', name='read_listings', strict=True,
        description='Read tools: ' + ' '.join(f'{key}: {value}' for key, value in CAPABILITIES.items()),
        parameters=dict(type='object', additionalProperties=False, required=['action', 'listing_id', 'terms', 'result_set_id', 'offer_id'],
            properties=dict(action=dict(type='string', enum=list(CAPABILITIES)),
                listing_id=dict(type=['string', 'null']), terms=dict(type='array', items=dict(type='string')),
                result_set_id=dict(type=['string', 'null']), offer_id=dict(type=['string', 'null'])))),
        dict(type='function', name='request_input', strict=True,
            description='Use choose_listing for an ambiguous item after lookup; search_terms for missing search input; '
                'choose_task when the goal itself is unclear; unsupported only when no registered tool can perform a clear goal. '
                'Do not infer blocked actions or failures: those require a real backend result.',
            parameters=dict(type='object', additionalProperties=False, required=['reason'],
                properties=dict(reason=dict(type='string', enum=['choose_listing', 'search_terms', 'choose_task', 'unsupported']))))]
    if workflows:
        from .assistant_listing_tools import catalog
        tools.extend(catalog())
        tools.append(dict(type='function', name='listing_workflow', strict=True,
            description='Start a new photo-first listing workflow only on an explicit create request, or resume '
                'the workflow linked to this thread. Resume with a real owned private listing_id to open its review. '
                'For questions about how creation works, do not start a session. This tool only opens the existing '
                'guided workflow; it never creates a listing, analyzes, publishes or sends a trade itself.',
            parameters=dict(type='object', additionalProperties=False, required=['mode', 'listing_id'],
                properties=dict(mode=dict(type='string', enum=['start', 'resume']), listing_id=dict(type=['string', 'null'])))))
    return tools


def outcome(status, actions=()):
    # Roundtrip through request validation: offered actions must be executable.
    for action in actions:
        ReadArguments.model_validate({key: value for key, value in action.items() if key != 'label'})
    return ReadOutcome(status=status, next_actions=list(actions)).model_dump()


def clarification(reason):
    if reason == 'choose_task':
        return dict(reply='What would you like help with: finding a listing, Marketplace matches, photos, saved preferences, or trade/shipment status?',
                    outcome=outcome('clarification', [dict(action='closet', label='Show my closet')]))
    if reason == 'choose_listing':
        return dict(reply='Which listing do you mean? Choose its title or number from the displayed items.',
                    outcome=outcome('clarification', [dict(action='closet', label='Show my closet')]))
    if reason == 'search_terms':
        return dict(reply='What would you like to browse in Marketplace? Tell me a brand, title, category, condition or size. Browsing is separate from trade matching.',
                    outcome=outcome('clarification'))
    return dict(reply='I can look up listings, show saved details/photos, check matches using Jouft’s fixed rules, read saved matching preferences, and check trade/shipment status. I cannot change matching rules or prices, accept trades, or make payments through these tools.',
                outcome=outcome('unsupported', [dict(action='closet', label='Show my closet')]))


def tool_failure():
    from fastapi import HTTPException
    return HTTPException(503, 'The read service could not complete your request. No changes were made. Retry the same saved request.',
                         headers={'X-Assistant-Outcome': 'tool_failure'})
