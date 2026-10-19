"""Versioned, shared photo identity; never persist prices or transfer item ownership."""
import copy
import hashlib
import json
import time

from .db import Database, utc_now_iso

IDENTITY_VERSION = 'listing-photo-identity-v2'
IDENTITY_FIELDS = (
    'candidate_brand', 'candidate_model', 'category', 'confidence',
    'model_identification', 'visual_signatures', 'visual_condition_assessment',
    'label_ocr', 'authenticity_screen', 'dupe_risk_assessment',
    'why_not_fast_fashion', 'shipping_profile',
)


def identity_fingerprint(images, *, category, brand_name, model, listing_id, owner_subject):
    # Order, filename, size, user condition and generated description do not
    # change the product's identity. Every supplied original is significant.
    if not listing_id or not owner_subject:
        raise ValueError('Persistent identity requires a listing and owner')
    document = dict(version=IDENTITY_VERSION, model=model, listing_id=listing_id, owner_subject=owner_subject,
        category=(category or '').strip().casefold(),
        brand_correction=(brand_name or 'unknown').strip().casefold(),
        photos=sorted(hashlib.sha256(image.bytes_data).hexdigest() for image in images))
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()


def extract_identity(profile):
    result = {key: copy.deepcopy(profile[key]) for key in IDENTITY_FIELDS if key in profile}
    result['identity_sources'] = copy.deepcopy(profile.get('identity_sources') or profile.get('grounding_sources') or [])
    result['_identity_origin'] = profile.get('_identity_origin') or 'gemini'
    return result


def reusable_identity(profile):
    model = profile.get('model_identification') or {}
    if not isinstance(model, dict):
        return False
    unknown = {'', 'unknown', 'n/a', 'none', 'unknown unknown'}
    try:
        confidence = float(model.get('confidence') or profile.get('confidence') or 0)
    except (ValueError, TypeError):
        return False
    # A formatter's neutral model score must not discard a strongly identified
    # garment with a directly readable brand label. Keep genuinely weak model
    # assessments below .5 ineligible, and never promote the reported confidence.
    ocr = profile.get('label_ocr') or {}
    candidates = [ocr, ocr.get('_batch_ocr_result')] if isinstance(ocr, dict) else []
    brand = str(profile.get('candidate_brand') or '').strip().casefold()
    def readable_label(row):
        if not isinstance(row, dict):
            return False
        raw = row.get('raw_visible_text') or ''
        raw = ' '.join(map(str, raw)) if isinstance(raw, list) else str(raw)
        try:
            score = float(row.get('confidence') or 0)
        except (TypeError, ValueError):
            return False
        return (score >= .85 and score <= 1 and brand
                and str(row.get('brand_text') or '').strip().casefold() == brand
                and brand in ' '.join(raw.casefold().split()))
    try:
        strong_label_identity = (confidence >= .5 and float(profile.get('confidence') or 0) >= .9
                                 and any(readable_label(row) for row in candidates))
    except (TypeError, ValueError):
        strong_label_identity = False
    return (str(profile.get('candidate_brand') or '').strip().casefold() not in unknown
            and str(model.get('name') or '').strip().casefold() not in unknown
            and (confidence >= .7 or strong_label_identity))


def resolve_identity(database_url, fingerprint, identify, *, timeout_s, listing_id, owner_subject):
    """Single-flight identification across jobs/processes, releasing read transactions."""
    db = Database(database_url)
    deadline = time.monotonic() + max(30, timeout_s)
    try:
        if not listing_id or not owner_subject:
            raise ValueError('Persistent identity requires a listing and owner')
        owner = db.fetchone(f'SELECT owner_subject FROM listings WHERE listing_id={db.param}', (listing_id,))
        db.commit()
        if not owner or owner[0] != owner_subject:
            raise ValueError('Persistent identity listing does not belong to this owner')
        while True:
            lock_key = hashlib.sha256(json.dumps([owner_subject, listing_id, fingerprint]).encode()).hexdigest()
            with db.analysis_execution_lock('product-identity:' + lock_key) as acquired:
                if acquired:
                    row = db.fetchone(f'SELECT identity_json FROM listing_product_identities WHERE '
                        f'owner_subject={db.param} AND listing_id={db.param} AND fingerprint={db.param}',
                        (owner_subject, listing_id, fingerprint))
                    db.commit()
                    if row:
                        return json.loads(row[0]), True
                    profile = identify()
                    if not isinstance(profile, dict):
                        raise ValueError('Product identification returned no usable profile')
                    identity = extract_identity(profile)
                    if reusable_identity(identity):
                        db.execute(f'INSERT INTO listing_product_identities '
                                   f'(owner_subject, listing_id, fingerprint, identity_json, created_at) '
                                   f'VALUES ({db.param}, {db.param}, {db.param}, {db.param}, {db.param}) '
                                   'ON CONFLICT (owner_subject, listing_id, fingerprint) DO NOTHING',
                                   (owner_subject, listing_id, fingerprint, json.dumps(identity), utc_now_iso()))
                        db.commit()
                    return identity, False
            if time.monotonic() >= deadline:
                raise TimeoutError('Timed out waiting for shared product identification')
            time.sleep(.1)
    finally:
        db.close()
