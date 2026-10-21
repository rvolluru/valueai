"""Read-only domain adapters shared by chat and HTTP routes.

No model decisions, conversation permissions or writes live here. Policy callbacks
are supplied by the application so extraction does not duplicate matching rules.
"""
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException


def saved_listing(listing_id, *, subject, db):
    """Reload a record at read time; old result IDs do not grant visibility."""
    item = db.get_listing_by_id(listing_id)
    if not item or (str(item.get('owner_subject') or '') != subject
                    and str(item.get('status') or '').lower() != 'active'):
        raise HTTPException(404, 'Listing not found')
    return item


def search_marketplace(items, terms, *, limit=12, offset=0):
    """Filter the caller's already-authorized Marketplace inventory, in order."""
    terms = [str(term).strip().casefold() for term in terms if str(term).strip()]
    matches = [item for item in items if all(term in ' '.join(
        str(item.get(key) or '') for key in ('brand', 'title', 'category', 'condition', 'size')
    ).casefold() for term in terms)]
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    page = matches[offset:offset + limit]
    next_offset = offset + len(page)
    return dict(count=len(matches), items=page, next_offset=next_offset if next_offset < len(matches) else None)


def listing_card(listing, *, public_image):
    """Shared safe presentation projection; no internal analysis or owner IDs."""
    gallery = []
    for value in [listing.get('image'), *(listing.get('images') or [])]:
        url = public_image(value)
        if url and url not in gallery:
            gallery.append(url)
    return dict(listing_id=str(listing.get('listing_id') or listing.get('id') or ''),
        title=listing.get('title') or 'Listing', brand=listing.get('brand') or 'Unknown brand',
        **{key: listing.get(key) for key in ('category', 'condition', 'size', 'status', 'owner_name')},
        image=gallery[0] if gallery else None, images=gallery[:6])


@dataclass(frozen=True)
class MatchRead:
    scope: Literal['one', 'all_eligible']
    source_listing_id: str | None = None
    source_limit: int = 12
    per_source_limit: int = 3

    def __post_init__(self):
        if self.scope not in {'one', 'all_eligible'}:
            raise ValueError('Unsupported match scope')
        if (self.scope == 'one') != bool(self.source_listing_id):
            raise ValueError('One source is required only for single-item scope')
        if not 1 <= self.source_limit <= 12 or not 1 <= self.per_source_limit <= 12:
            raise ValueError('Match read exceeds supported bounds')


def grouped_matches(query: MatchRead, *, owned_listings, read_source):
    """Preserve each source/target relationship; never infer an offered item."""
    if query.scope == 'one':
        sources = [item for item in owned_listings if str(item.get('listing_id')) == query.source_listing_id]
        if not sources:
            raise HTTPException(404, 'Listing not found')
    else:
        sources = [item for item in owned_listings if str(item.get('status') or '').lower() == 'active'
                   and float(item.get('estimated_value') or 0) > 0][:query.source_limit]
    groups = []
    for source in sources:
        result = read_source(str(source['listing_id']), query.per_source_limit)
        groups.append(dict(source_listing_id=str(source['listing_id']),
            source_title=source.get('title') or 'Your item', count=result['count'],
            items=result['items'], has_more=result.get('has_more', False), next_offset=result.get('next_offset')))
    return groups


def marketplace_matches(listing_id, *, subject, db, limit, offset,
                        matches_preferences, tolerance_for, sent_pairs, hydrate):
    """Authoritative owned-source matching read, also used by the public route."""
    source = db.get_listing_by_id(listing_id)
    if not source or str(source.get('owner_subject') or '') != subject:
        raise HTTPException(404, 'Listing not found')
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    profile = db.get_user_profile_quiz(subject)
    pairs = sent_pairs(db, subject)
    value = float(source.get('estimated_value') or 0)
    items = []
    if str(source.get('status') or '').lower() == 'active' and value > 0:
        for target in db.list_recent_listings(limit=5000, include_analysis=False, include_media=True, active_only=True):
            target_id = str(target.get('listing_id') or '')
            if not target_id or target_id == listing_id or str(target.get('owner_subject') or '') == subject:
                continue
            if (target_id, listing_id) in pairs or not matches_preferences(target, profile):
                continue
            target_value = float(target.get('estimated_value') or 0)
            if target_value <= 0 or abs(value - target_value) > tolerance_for(target_value)[0]:
                continue
            items.append(hydrate(target))
    page = items[offset:offset + limit]
    next_offset = offset + len(page)
    return dict(count=len(items), limit=limit, offset=offset,
                next_offset=next_offset if next_offset < len(items) else None,
                has_more=next_offset < len(items), items=page)


def matching_preferences(*, subject, db):
    profile = db.get_user_profile_quiz(subject) or {}
    return {key: profile.get(key) for key in ('category_preferences', 'tops_size', 'dresses_size', 'bottoms_size', 'shoes_size')}


def trade_status(*, subject, db, offer_id=None, shipping=False, pending_only=False):
    offers = [db.get_trade_offer_by_id(offer_id)] if offer_id else db.list_trade_offers_for_subject(subject, limit=50)
    offers = [item for item in offers if item and subject in {item.get('from_subject'), item.get('to_subject')}]
    if offer_id and not offers:
        raise HTTPException(404, 'Trade not found')
    if pending_only:
        offers = [item for item in offers if item.get('status') == 'pending']
    result = []
    for offer in offers:
        listing = db.get_listing_by_id(offer.get('target_listing_id')) or {}
        title = listing.get('title') or 'Trade item'
        if not shipping:
            result.append(dict(offer_id=offer['offer_id'], title=title, status=offer.get('status') or 'Unknown'))
        else:
            for shipment in db.list_shipments_for_offer(offer['offer_id']):
                if subject not in {shipment.get('from_subject'), shipment.get('to_subject')}:
                    continue
                result.append(dict(offer_id=offer['offer_id'], title=title,
                    carrier=shipment.get('carrier') or 'Carrier pending',
                    status=shipment.get('tracking_status') or shipment.get('status') or 'Status pending',
                    eta=shipment.get('tracking_eta'), updated_at=shipment.get('tracking_status_updated_at')))
    return result
