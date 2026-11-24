"""Admin-managed trial offers. Local access never implies permission to charge."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

from .auth import require_admin_user, require_clerk_user
from .db import Database, TrialListingLimitError
from .deps import get_db, get_settings

router = APIRouter()
PLANS = {'starter_15': ('Starter', 1500, 16200), 'pro_25': ('Pro', 2500, 27000)}


def now():
    return datetime.now(timezone.utc)


def code_hash(code):
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


class OfferInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(default_factory=lambda: secrets.token_hex(8).upper(), pattern=r'^[A-Za-z0-9-]{6,64}$')
    plan: Literal['starter_15', 'pro_25'] = 'starter_15'
    duration_days: int = Field(default=30, ge=1, le=365)
    listing_limit: int | None = Field(default=25, ge=1, le=2147483647)
    require_card: bool = False
    end_behavior: Literal['expire', 'renew'] = 'expire'
    billing_cycle: Literal['monthly', 'annual'] = 'monthly'
    max_redemptions: int = Field(default=100, ge=1, le=100000)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    allowed_emails: list[str] = Field(default_factory=list, max_length=500)
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    first_trial_only: bool = True
    new_subscribers_only: bool = True

    @model_validator(mode='after')
    def validate_policy(self):
        if self.end_behavior == 'renew' and not self.require_card:
            raise ValueError('Automatic renewal requires a card')
        for field in ('starts_at', 'expires_at'):
            value = getattr(self, field)
            if value and value.tzinfo is None:
                raise ValueError('Dates must include a timezone')
        if self.expires_at and self.expires_at <= (self.starts_at or now()):
            raise ValueError('Redemption expiry must follow the start date')
        self.allowed_emails = sorted(set(e.strip().lower() for e in self.allowed_emails))
        self.allowed_domains = sorted(set(d.strip().lower().lstrip('@') for d in self.allowed_domains))
        if any(not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', e) for e in self.allowed_emails):
            raise ValueError('Invalid restricted email')
        if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}', d) for d in self.allowed_domains):
            raise ValueError('Invalid restricted email domain')
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('Name cannot be blank')
        return self


class OfferToggle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    active: bool


class RedeemInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(min_length=6, max_length=64)
    consent: bool = False
    offer_version: str | None = Field(default=None, max_length=64)


class SyncInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: str = Field(pattern=r'^cs_[A-Za-z0-9_]+$', max_length=255)


@contextmanager
def transaction(db):
    # Use a separate connection for Postgres/file SQLite: never commit another
    # request's transaction on the application's cached Database instance.
    owned = db.url != 'sqlite:///:memory:'
    conn = Database(db.url) if owned else db
    try:
        with conn._sqlite_lock:
            if conn._sqlite_conn is not None:
                conn.execute('BEGIN IMMEDIATE')
            else:
                conn.fetchone('SELECT pg_advisory_xact_lock(1967052026)')
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    finally:
        if owned:
            conn.close()


def rows(db, table, where='', values=()):
    return db._fetch_dicts('SELECT * FROM ' + table + (' WHERE ' + where if where else ''), values)


def policy(row):
    return json.loads(row['config_json'])


def active_grant(db, subject):
    found = db._fetch_dicts(f'''SELECT * FROM invitation_trial_redemptions
        WHERE owner_subject={db.param} AND state='active' AND ends_at>{db.param}
        ORDER BY ends_at DESC LIMIT 1''', (subject, now().isoformat()))
    return found[0] if found else None


def effective_profile(db, subject, profile):
    grant = active_grant(db, subject)
    billing = db.get_billing_profile(subject) or {}
    if grant and str(billing.get('subscription_status') or '').lower() not in {'active', 'trialing', 'canceling', 'past_due'}:
        return {**profile, 'subscription_plan': grant['plan'], 'subscription_status': 'trialing',
                'subscription_renewal_date': grant['ends_at'], 'subscription_trial': public_grant(grant, db)}
    return profile


def public_grant(grant, db=None):
    result = {k: grant.get(k) for k in ('redemption_id', 'offer_id', 'plan', 'state', 'starts_at', 'ends_at', 'end_behavior')}
    result['access_status'] = ('expired' if grant.get('ends_at') and grant['ends_at'] <= now().isoformat()
                               and grant['state'] in {'active','converted'} else grant['state'])
    limit = json.loads(grant['config_json']).get('listing_limit')
    used = db.fetchone(f'SELECT COUNT(*) FROM invitation_trial_listing_usage WHERE redemption_id={db.param}', (grant['redemption_id'],))[0] if db is not None else None
    result.update(listing_limit=limit, listings_used=used, listings_remaining=max(0,limit-used) if limit is not None and used is not None else None)
    return result



def verified_email(principal, settings):
    # Never trust the editable profile email for eligibility or one-trial rules.
    if not settings.clerk_secret_key:
        raise HTTPException(503, 'Verified account email is temporarily unavailable')
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get('https://api.clerk.com/v1/users/' + principal.subject,
                                  headers={'Authorization': 'Bearer ' + settings.clerk_secret_key})
            response.raise_for_status()
            user = response.json()
        address = next(a for a in user.get('email_addresses', []) if
                       a.get('id') == user.get('primary_email_address_id') and
                       a.get('verification', {}).get('status') == 'verified')
        return address['email_address'].strip().lower()
    except Exception:
        raise HTTPException(403, 'A verified primary account email is required')


def throttle(db, subject):
    bucket = now().strftime('%Y-%m-%dT%H:%M')
    with transaction(db) as tx:
        tx.execute(f'''INSERT INTO invitation_trial_attempts (owner_subject,bucket,attempts)
            VALUES ({tx.param},{tx.param},1) ON CONFLICT (owner_subject,bucket)
            DO UPDATE SET attempts=invitation_trial_attempts.attempts+1''', (subject, bucket))
        count = tx.fetchone(f'SELECT attempts FROM invitation_trial_attempts WHERE owner_subject={tx.param} AND bucket={tx.param}', (subject, bucket))[0]
        tx.execute(f'DELETE FROM invitation_trial_attempts WHERE bucket<{tx.param}', ((now()-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),))
    if count > 10:
        raise HTTPException(429, 'Too many attempts. Please try again in a minute.')


def eligible(tx, code, subject, email):
    found = rows(tx, 'invitation_trial_offers', f'code_hash={tx.param}', (code_hash(code),))
    if not found:
        raise HTTPException(400, 'Invitation is invalid or unavailable')
    offer = found[0]
    cfg = policy(offer)
    stamp = now().isoformat()
    if not offer['active'] or (cfg['starts_at'] and cfg['starts_at'] > stamp) or (cfg['expires_at'] and cfg['expires_at'] <= stamp):
        raise HTTPException(400, 'Invitation is invalid or unavailable')
    if (cfg['allowed_emails'] or cfg['allowed_domains']) and email not in cfg['allowed_emails'] and email.split('@')[-1] not in cfg['allowed_domains']:
        raise HTTPException(403, 'This invitation is not available for your account')
    billing = tx.get_billing_profile(subject) or {}
    if billing.get('stripe_subscription_id') and str(billing.get('subscription_status') or '') not in {'canceled', 'cancelled', 'incomplete_expired'}:
        raise HTTPException(409, 'An existing subscription must be managed before starting an invitation trial')
    base = tx.get_user_profile_quiz(subject) or {}
    if any(str(record.get('subscription_plan') or 'free') != 'free' and str(record.get('subscription_status') or '') in {'active','trialing','canceling','past_due'} for record in (billing,base)):
        raise HTTPException(409, 'An existing membership must be managed before starting a trial')
    if active_grant(tx, subject):
        raise HTTPException(409, 'You already have an active invitation trial')
    previous = rows(tx, 'invitation_trial_redemptions', f'(owner_subject={tx.param} OR email={tx.param}) AND state IN (\'active\',\'converted\',\'revoked\')', (subject, email))
    if any(r['offer_id'] == offer['offer_id'] for r in previous) or (cfg['first_trial_only'] and previous):
        raise HTTPException(409, 'This account has already used the trial allowance')
    if cfg['new_subscribers_only'] and (billing.get('stripe_subscription_id') or
            str(billing.get('subscription_status') or '') in {'active', 'trialing', 'canceling', 'past_due'}):
        raise HTTPException(409, 'This invitation is only for new subscribers')
    return offer, cfg


def offer_version(cfg):
    return hashlib.sha256(json.dumps({"config":cfg,"price":PLANS[cfg["plan"]]},sort_keys=True).encode()).hexdigest()


def preview(cfg):
    label, monthly, annual = PLANS[cfg['plan']]
    cents = annual if cfg['billing_cycle'] == 'annual' else monthly
    return {k: cfg[k] for k in ('name', 'plan', 'duration_days', 'require_card', 'end_behavior', 'billing_cycle')} | {
        'listing_limit': cfg.get('listing_limit'), 'offer_version': offer_version(cfg), 'renewal_amount_cents': cents if cfg['end_behavior'] == 'renew' else 0, 'currency': 'usd',
        'summary': f"{label} membership for {cfg['duration_days']} days. " + (
            f"Then ${cents/100:.2f} USD {'per year' if cfg['billing_cycle']=='annual' else 'per month'} until canceled."
            if cfg['end_behavior'] == 'renew' else 'Membership trial expires without a charge.') +
            (' A card is required.' if cfg['require_card'] else ' No card required.') +
            (' Unlimited new listings during the trial.' if cfg.get('listing_limit') is None else f" Up to {cfg['listing_limit']} new listings total during the trial.") +
            ' Shipping and trade charges are not included.'}


@router.post('/v1/admin/trial-invitations')
def create_offer(payload: OfferInput, principal=Depends(require_admin_user), db=Depends(get_db)):
    cfg = payload.model_dump(mode='json')
    code = cfg.pop('code').strip().upper()
    # Normalize timestamps to UTC for consistent lexical comparisons in both DBs.
    for key in ('starts_at', 'expires_at'):
        if cfg[key]: cfg[key] = datetime.fromisoformat(cfg[key]).astimezone(timezone.utc).isoformat()
    offer_id = str(uuid.uuid4())
    with transaction(db) as tx:
        if tx.fetchone(f'SELECT offer_id FROM invitation_trial_offers WHERE code_hash={tx.param}', (code_hash(code),)):
            raise HTTPException(409, 'Code is already in use')
        tx.execute(f'''INSERT INTO invitation_trial_offers
            (offer_id,code_hash,code_hint,config_json,active,created_by,created_at,updated_at)
            VALUES ({','.join([tx.param]*8)})''', (offer_id, code_hash(code), code[-4:], json.dumps(cfg), 1, principal.subject, now().isoformat(), now().isoformat()))
    return {'offer_id': offer_id, 'code': code, 'config': cfg, 'active': True}


@router.put('/v1/admin/trial-invitations/{offer_id}')
def update_offer(offer_id: str, payload: OfferInput, principal=Depends(require_admin_user), db=Depends(get_db)):
    if 'code' in payload.model_fields_set:
        raise HTTPException(400, 'Codes are immutable. Create a new invitation to change the code.')
    cfg = payload.model_dump(mode='json', exclude={'code'})
    for key in ('starts_at', 'expires_at'):
        if cfg[key]: cfg[key] = datetime.fromisoformat(cfg[key]).astimezone(timezone.utc).isoformat()
    with transaction(db) as tx:
        if not rows(tx, 'invitation_trial_offers', f'offer_id={tx.param}', (offer_id,)):
            raise HTTPException(404, 'Invitation not found')
        consumed = tx.fetchone(f"SELECT COUNT(*) FROM invitation_trial_redemptions WHERE offer_id={tx.param} AND state IN ('active','converted','pending','revoked')", (offer_id,))[0]
        if cfg['max_redemptions'] < consumed:
            raise HTTPException(409, 'Redemption limit cannot be less than the places already used or reserved')
        tx.execute(f'UPDATE invitation_trial_offers SET config_json={tx.param},updated_at={tx.param} WHERE offer_id={tx.param}', (json.dumps(cfg),now().isoformat(),offer_id))
        tx.execute(f'INSERT INTO invitation_trial_audit (audit_id,offer_id,actor_subject,action,created_at) VALUES ({",".join([tx.param]*5)})',
                   (str(uuid.uuid4()),offer_id,principal.subject,'settings_updated',now().isoformat()))
    return {'offer_id':offer_id,'config':cfg}


@router.get('/v1/admin/trial-invitations')
def list_offers(principal=Depends(require_admin_user), db=Depends(get_db)):
    offers = rows(db, 'invitation_trial_offers')
    return {'offers': [{**{k:r[k] for k in ('offer_id','code_hint','active','created_at','created_by')}, 'config': policy(r),
                       'audit': rows(db, 'invitation_trial_audit', f'offer_id={db.param}', (r['offer_id'],)), 'redemptions': [public_grant(g, db) | {'owner_subject':g['owner_subject'], 'email':g['email']} for g in
                                       rows(db,'invitation_trial_redemptions', f'offer_id={db.param}', (r['offer_id'],))]}
                      for r in sorted(offers,key=lambda r:r['created_at'],reverse=True)]}


@router.patch('/v1/admin/trial-invitations/{offer_id}')
def toggle_offer(offer_id: str, payload: OfferToggle, principal=Depends(require_admin_user), db=Depends(get_db)):
    with transaction(db) as tx:
        if not rows(tx, 'invitation_trial_offers', f'offer_id={tx.param}', (offer_id,)):
            raise HTTPException(404, 'Invitation not found')
        tx.execute(f'UPDATE invitation_trial_offers SET active={tx.param},updated_at={tx.param} WHERE offer_id={tx.param}',
                   (int(payload.active),now().isoformat(),offer_id))
        tx.execute(f'INSERT INTO invitation_trial_audit (audit_id,offer_id,actor_subject,action,created_at) VALUES ({",".join([tx.param]*5)})',
                   (str(uuid.uuid4()),offer_id,principal.subject,'enabled' if payload.active else 'disabled',now().isoformat()))
    return {'offer_id':offer_id,'active':payload.active}


@router.post('/v1/me/trial-invitations/preview')
def preview_offer(payload: RedeemInput, principal=Depends(require_clerk_user), db=Depends(get_db), settings=Depends(get_settings)):
    throttle(db, principal.subject)
    email = verified_email(principal, settings)
    with transaction(db) as tx:
        offer, cfg = eligible(tx, payload.code, principal.subject, email)
        consumed = tx.fetchone(f"SELECT COUNT(*) FROM invitation_trial_redemptions WHERE offer_id={tx.param} AND state IN ('active','converted','pending','revoked')", (offer['offer_id'],))[0]
        if consumed >= cfg['max_redemptions']:
            raise HTTPException(409, 'This invitation has reached its redemption limit')
    return preview(cfg)


@router.get('/v1/me/trial-invitations')
def my_trials(principal=Depends(require_clerk_user), db=Depends(get_db), settings=Depends(get_settings)):
    # Recovery after closing the browser/mobile app: possession of a return URL
    # never grants access, and the session belongs to the authenticated subject.
    pending = rows(db, 'invitation_trial_redemptions', f"owner_subject={db.param} AND state='pending'", (principal.subject,))
    for grant in pending:
        if grant.get('checkout_session_id'):
            session = stripe_request(settings, 'GET', 'checkout/sessions/' + grant['checkout_session_id'])
            complete_checkout(db, settings, session)
    grant = active_grant(db, principal.subject)
    if not grant:
        candidates = rows(db, 'invitation_trial_redemptions', f"owner_subject={db.param} AND state='converted' AND ends_at>{db.param}", (principal.subject, now().isoformat()))
        billing_state = (db.get_billing_profile(principal.subject) or {}).get('subscription_status')
        grant = candidates[-1] if candidates and billing_state in {'active','trialing','canceling'} else None
    billing = db.get_billing_profile(principal.subject) or {}
    return {'trial': public_grant(grant, db) if grant else None, 'subscription_status': billing.get('subscription_status')}



def stripe_request(settings, method, path, *, data=None, key=None):
    if not settings.stripe_secret_key:
        raise HTTPException(503, 'Card-based trials are not configured')
    try:
        with httpx.Client(timeout=20) as client:
            response = client.request(method, 'https://api.stripe.com/v1/' + path,
                                      auth=(settings.stripe_secret_key, ''), data=data,
                                      headers={'Idempotency-Key': key} if key else {})
            response.raise_for_status()
            return response.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Billing provider unavailable. Retry this invitation; no new trial will be created.')


def checkout_for_grant(db, settings, grant, cfg):
    if grant.get('checkout_session_id'):
        session = stripe_request(settings, 'GET', 'checkout/sessions/' + grant['checkout_session_id'])
        if session.get('status') == 'expired':
            complete_checkout(db, settings, session)
            raise HTTPException(409, 'Checkout expired. Redeem the invitation again.')
        return {'status': 'checkout', 'checkout_url': session.get('url'), 'session_id':session['id']}
    subject = grant['owner_subject']
    customer = db.get_stripe_customer_id(subject)
    if not customer:
        result = stripe_request(settings,'POST','customers',data={'email':grant['email'],'metadata[owner_subject]':subject}, key='trial-customer-'+subject)
        customer = result['id']
        db.set_stripe_customer_id(subject,customer)
    public_url = str(settings.public_app_url or '').rstrip('/')
    parsed = urlsplit(public_url)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(503, 'Application return URL is not configured')
    data = {
        'mode': 'subscription' if cfg['end_behavior']=='renew' else 'setup',
        'customer': customer, 'payment_method_types[]':'card',
        'success_url': public_url + '/?tab=profile&trial_session_id={CHECKOUT_SESSION_ID}',
        'cancel_url': public_url + '/?tab=profile&trial_canceled=1',
        'expires_at':str(int(datetime.fromisoformat(grant['reserved_until']).timestamp())),
        'metadata[trial_redemption_id]':grant['redemption_id'],
        'metadata[owner_subject]':subject,
        'custom_text[submit][message]':preview(cfg)['summary'],
    }
    if cfg['end_behavior']=='renew':
        label,monthly,annual=PLANS[cfg['plan']]
        data.update({
            'payment_method_collection':'always',
            'line_items[0][price_data][currency]':'usd',
            'line_items[0][price_data][unit_amount]':str(annual if cfg['billing_cycle']=='annual' else monthly),
            'line_items[0][price_data][recurring][interval]':'year' if cfg['billing_cycle']=='annual' else 'month',
            'line_items[0][price_data][product_data][name]':'Jouft '+label+' membership',
            'line_items[0][quantity]':'1',
            'subscription_data[trial_period_days]':str(cfg['duration_days']),
            'subscription_data[trial_settings][end_behavior][missing_payment_method]':'cancel',
            'subscription_data[metadata][owner_subject]':subject,
            'subscription_data[metadata][plan]':cfg['plan'],
            'subscription_data[metadata][billing_cycle]':cfg['billing_cycle'],
            'subscription_data[metadata][trial_redemption_id]':grant['redemption_id'],
        })
    else:
        data['setup_intent_data[metadata][trial_redemption_id]']=grant['redemption_id']
    session = stripe_request(settings,'POST','checkout/sessions',data=data,key='trial-checkout-'+grant['redemption_id'])
    with transaction(db) as tx:
        tx.execute(f'UPDATE invitation_trial_redemptions SET checkout_session_id={tx.param} WHERE redemption_id={tx.param}',(session['id'],grant['redemption_id']))
    return {'status':'checkout','checkout_url':session['url'],'session_id':session['id']}


@router.post('/v1/me/trial-invitations/redeem')
def redeem_offer(payload: RedeemInput, principal=Depends(require_clerk_user), db=Depends(get_db), settings=Depends(get_settings)):
    throttle(db,principal.subject)
    email=verified_email(principal,settings)
    with transaction(db) as tx:
        tx.execute(f"UPDATE invitation_trial_redemptions SET state='failed' WHERE state='pending' AND checkout_session_id IS NULL AND reserved_until<={tx.param}", (now().isoformat(),))
        existing = tx._fetch_dicts(f'''SELECT r.* FROM invitation_trial_redemptions r
            JOIN invitation_trial_offers o ON r.offer_id=o.offer_id
            WHERE o.code_hash={tx.param} AND r.owner_subject={tx.param} AND r.state IN ('active','converted','pending','revoked')
            ORDER BY r.created_at DESC''', (code_hash(payload.code),principal.subject))
        if existing:
            grant=existing[0]
            if grant['state'] != 'pending':
                return {'status':'already_redeemed','trial':public_grant(grant, db)}
            cfg=json.loads(grant['config_json'])
        else:
            offer,cfg=eligible(tx,payload.code,principal.subject,email)
            if payload.offer_version != offer_version(cfg):
                raise HTTPException(409, 'The offer changed. Check the invitation and review its terms again.')
            if not payload.consent:
                raise HTTPException(400,'Review and confirm the trial terms before redeeming')
            if cfg['require_card'] and not settings.stripe_secret_key:
                raise HTTPException(503,'Card-based trials are not configured')
            pending=rows(tx,'invitation_trial_redemptions',f'(owner_subject={tx.param} OR email={tx.param}) AND state=\'pending\'',(principal.subject,email))
            if pending:
                raise HTTPException(409,'Finish or let your existing trial checkout expire before using another invitation')
            consumed=tx.fetchone(f"SELECT COUNT(*) FROM invitation_trial_redemptions WHERE offer_id={tx.param} AND state IN ('active','converted','pending','revoked')",(offer['offer_id'],))[0]
            if consumed>=cfg['max_redemptions']:
                raise HTTPException(409,'This invitation has reached its redemption limit')
            stamp=now()
            grant={'redemption_id':str(uuid.uuid4()),'offer_id':offer['offer_id'],'owner_subject':principal.subject,'email':email,
                   'plan':cfg['plan'],'state':'pending' if cfg['require_card'] else 'active',
                   'starts_at':None if cfg['require_card'] else stamp.isoformat(),
                   'ends_at':None if cfg['require_card'] else (stamp+timedelta(days=cfg['duration_days'])).isoformat(),
                   'end_behavior':cfg['end_behavior'],'config_json':json.dumps(cfg),'checkout_session_id':None,'stripe_subscription_id':None,
                   'reserved_until':(stamp+timedelta(hours=1)).isoformat(),'created_at':stamp.isoformat(),
                   'consent_at':stamp.isoformat(),'consent_text':preview(cfg)['summary']}
            tx.execute(f'INSERT INTO invitation_trial_redemptions ({",".join(grant)}) VALUES ({",".join([tx.param]*len(grant))})',tuple(grant.values()))
    if grant['state']=='active':
        return {'status':'active','trial':public_grant(grant, db)}
    return checkout_for_grant(db,settings,grant,cfg)


def complete_checkout(db, settings, session):
    redemption_id=(session.get('metadata') or {}).get('trial_redemption_id')
    if not redemption_id:
        return {'handled':False}
    # Fetch the authoritative session on sync; signed webhooks supply a trusted object.
    records=rows(db,'invitation_trial_redemptions',f'redemption_id={db.param}',(redemption_id,))
    if not records:
        return {'handled':False}
    grant=records[0]
    if session.get('metadata',{}).get('owner_subject') != grant['owner_subject']:
        raise HTTPException(400,'Checkout account does not match the invitation')
    if grant.get('checkout_session_id') and session.get('id')!=grant['checkout_session_id']:
        raise HTTPException(400,'Checkout does not match the invitation')
    subscription=None
    if session.get('status')=='complete' and grant['end_behavior']=='renew':
        subscription=stripe_request(settings,'GET','subscriptions/'+session['subscription'])
        if subscription.get('status') not in {'trialing','active','canceled','past_due','unpaid'}:
            raise HTTPException(409,'Subscription is not ready; refresh trial status shortly')
        if (subscription.get('metadata') or {}).get('trial_redemption_id')!=redemption_id:
            raise HTTPException(400,'Subscription does not match invitation')
    if session.get('status')=='complete' and grant['end_behavior']=='expire':
        setup=stripe_request(settings,'GET','setup_intents/'+session['setup_intent'])
        if setup.get('status')!='succeeded' or not setup.get('payment_method'):
            raise HTTPException(409,'Card setup is not complete')
    with transaction(db) as tx:
        current=rows(tx,'invitation_trial_redemptions',f'redemption_id={tx.param}',(redemption_id,))[0]
        if current['state']!='pending':
            return {'handled':True,'trial':public_grant(current, tx)}
        if session.get('status')=='expired':
            tx.execute(f"UPDATE invitation_trial_redemptions SET state='expired' WHERE redemption_id={tx.param}",(redemption_id,))
            return {'handled':True,'status':'expired'}
        if session.get('status')!='complete':
            return {'handled':True,'status':'pending'}
        cfg=json.loads(current['config_json'])
        start=datetime.fromtimestamp(subscription['trial_start'],timezone.utc) if subscription else now()
        end=datetime.fromtimestamp(subscription['trial_end'],timezone.utc) if subscription else start+timedelta(days=cfg['duration_days'])
        state='converted' if subscription else 'active'
        tx.execute(f'UPDATE invitation_trial_redemptions SET state={tx.param},starts_at={tx.param},ends_at={tx.param},checkout_session_id={tx.param},stripe_subscription_id={tx.param} WHERE redemption_id={tx.param}',
                   (state,start.isoformat(),end.isoformat(),session['id'],subscription['id'] if subscription else None,redemption_id))
        if subscription:
            # Subsequent renewals/cancellations use existing signed Stripe webhooks.
            stamp = now().isoformat()
            tx.execute(f"""INSERT INTO user_billing_profiles
                (owner_subject,stripe_subscription_id,subscription_plan,subscription_billing_cycle,subscription_status,subscription_renewal_date,created_at,updated_at)
                VALUES ({','.join([tx.param]*8)}) ON CONFLICT(owner_subject) DO UPDATE SET
                stripe_subscription_id=excluded.stripe_subscription_id,subscription_plan=excluded.subscription_plan,
                subscription_billing_cycle=excluded.subscription_billing_cycle,subscription_status=excluded.subscription_status,
                subscription_renewal_date=excluded.subscription_renewal_date,updated_at=excluded.updated_at""",
                (current['owner_subject'],subscription['id'],cfg['plan'],cfg['billing_cycle'],subscription['status'],end.isoformat(),stamp,stamp))
            tx.execute(f"""UPDATE user_profiles SET subscription_plan={tx.param},subscription_billing_cycle={tx.param},
                subscription_status={tx.param},subscription_renewal_date={tx.param},updated_at={tx.param} WHERE owner_subject={tx.param}""",
                (cfg['plan'],cfg['billing_cycle'],subscription['status'],end.isoformat(),stamp,current['owner_subject']))
        return {'handled':True,'status':state,'trial':public_grant({**current,'state':state,'starts_at':start.isoformat(),'ends_at':end.isoformat()}, tx)}


@router.post('/v1/me/trial-invitations/sync')
def sync_checkout(payload: SyncInput, principal=Depends(require_clerk_user), db=Depends(get_db), settings=Depends(get_settings)):
    throttle(db, principal.subject)
    session=stripe_request(settings,'GET','checkout/sessions/'+payload.session_id)
    if session.get('metadata',{}).get('owner_subject')!=principal.subject:
        raise HTTPException(403,'Checkout belongs to a different account')
    return complete_checkout(db,settings,session)


@router.post('/v1/admin/trial-invitations/redemptions/{redemption_id}/revoke')
def revoke_local_trial(redemption_id: str, principal=Depends(require_admin_user), db=Depends(get_db)):
    with transaction(db) as tx:
        grants = rows(tx, 'invitation_trial_redemptions', f'redemption_id={tx.param}', (redemption_id,))
        if not grants:
            raise HTTPException(404, 'Trial not found')
        grant = grants[0]
        if grant['state'] == 'revoked':
            return {'status':'revoked'}
        if grant['end_behavior'] != 'expire' or grant['state'] != 'active':
            raise HTTPException(409, 'Only an active no-charge trial can be ended here. Manage recurring subscriptions through billing.')
        tx.execute(f"UPDATE invitation_trial_redemptions SET state='revoked' WHERE redemption_id={tx.param}", (redemption_id,))
        tx.execute(f'INSERT INTO invitation_trial_audit (audit_id,offer_id,actor_subject,action,created_at) VALUES ({",".join([tx.param]*5)})',
                   (str(uuid.uuid4()),grant['offer_id'],principal.subject,'trial_revoked:'+redemption_id,now().isoformat()))
    return {'status':'revoked'}


def allowance_grant(db, subject):
    billing = db.get_billing_profile(subject) or {}
    grant = active_grant(db, subject)
    paid_status = str(billing.get('subscription_status') or '') in {'active','trialing','canceling','past_due'}
    if grant and not paid_status:
        return grant
    if paid_status:
        candidates = rows(db, 'invitation_trial_redemptions',
                          f"owner_subject={db.param} AND state='converted' AND ends_at>{db.param}",
                          (subject, now().isoformat()))
        return next((r for r in candidates if r.get('stripe_subscription_id') == billing.get('stripe_subscription_id')), None)
    return None


def insert_listing_with_allowance(db, values):
    # Listing creation and slot consumption commit together. All insert paths,
    # including assistant-created drafts, pass through Database.insert_listing.
    with transaction(db) as tx:
        grant = allowance_grant(tx, values['owner_subject'])
        if grant:
            limit = json.loads(grant['config_json']).get('listing_limit')
            used = tx.fetchone(f'SELECT COUNT(*) FROM invitation_trial_listing_usage WHERE redemption_id={tx.param}', (grant['redemption_id'],))[0]
            if limit is not None and used >= limit:
                raise TrialListingLimitError(f'Trial listing allowance reached ({limit}). Existing listings can still be edited; choose a paid plan to create more.')
        created_at = tx._insert_listing_unchecked(_commit=False, **values)
        if grant:
            tx.execute(f'INSERT INTO invitation_trial_listing_usage (listing_id,redemption_id,created_at) VALUES ({tx.param},{tx.param},{tx.param})',
                       (values['listing_id'],grant['redemption_id'],created_at))
    if values.get('source_item_id'):
        db.link_analysis_item(values['source_item_id'],values['listing_id'],values['owner_subject'])
    return created_at
