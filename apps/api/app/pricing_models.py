"""Durable listing pricing cohorts. No implicit cross-model retry/fallback."""
from .db import Database, utc_now_iso

VERSION = 'sticky-listing-pricing-v1'
LEGACY_MODEL = 'gpt-5'


def resolve_pricing_model(database_url, listing_id, owner_subject, *, new_model, inherited_model=None):
    """First assignment wins across workers; listing ownership never transfers."""
    if not listing_id or not owner_subject or not new_model:
        raise ValueError('Pricing routing requires listing, owner and configured model')
    db = Database(database_url)
    try:
        listing = db.fetchone(f'SELECT owner_subject FROM listings WHERE listing_id={db.param}', (listing_id,))
        if not listing or listing[0] != owner_subject:
            raise ValueError('Pricing-model listing does not belong to owner')
        db.execute(f'INSERT INTO listing_pricing_models (listing_id,owner_subject,model,reason,assigned_at) '
            f'VALUES ({db.param},{db.param},{db.param},{db.param},{db.param}) '
            'ON CONFLICT (listing_id) DO NOTHING',
            (listing_id, owner_subject, inherited_model or new_model,
             'reused_analysis' if inherited_model else 'new_listing', utc_now_iso()))
        db.commit()
        row = db.fetchone(f'SELECT owner_subject,model,reason,assigned_at FROM listing_pricing_models '
            f'WHERE listing_id={db.param}', (listing_id,))
        db.commit()
        if row[0] != owner_subject:
            raise ValueError('Pricing-model assignment owner mismatch')
        return dict(version=VERSION, listing_id=listing_id, owner_subject=owner_subject,
                    model=row[1], reason=row[2], assigned_at=row[3])
    finally:
        db.close()


def analysis_pricing_model(analysis):
    profile = (analysis or {}).get('item_profile') or {}
    return ((profile.get('_workflow') or {}).get('pricing_model_assignment') or {}).get('model') or LEGACY_MODEL
