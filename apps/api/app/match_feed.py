"""Daily match observations and SES digest delivery; no AI calls or listing writes."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, StrictBool

from .db import Database
from .deps import get_db
from .auth import AuthPrincipal, get_request_principal

router = APIRouter()


class EmailUpdatePreference(BaseModel):
    subscribed: StrictBool


def account_email(db, principal):
    profile = db.get_user_profile_quiz(principal.subject) or {}
    email = str(profile.get('email') or '').strip().lower()
    if not email:
        raise HTTPException(409, 'Save an email address in your profile first.')
    return email


@router.get('/v1/me/email-updates')
def read_email_updates(principal: AuthPrincipal = Depends(get_request_principal), db: Database = Depends(get_db)):
    return {'subscribed': not bool(preference(db, account_email(db, principal), datetime.now(timezone.utc))[0])}


@router.put('/v1/me/email-updates')
def update_email_updates(body: EmailUpdatePreference, principal: AuthPrincipal = Depends(get_request_principal),
                         db: Database = Depends(get_db)):
    email = account_email(db, principal)
    now = datetime.now(timezone.utc)
    preference(db, email, now)
    db.execute(f'UPDATE email_update_preferences SET unsubscribed={db.param}, updated_at={db.param} WHERE email={db.param}',
               (0 if body.subscribed else 1, now.isoformat(), email))
    db.commit()
    return {'subscribed': body.subscribed}


def preference(db, email, now):
    email = email.strip().lower()
    db.execute(f'''INSERT INTO email_update_preferences (email, token, updated_at)
        VALUES ({db.param}, {db.param}, {db.param}) ON CONFLICT (email) DO NOTHING''',
        (email, secrets.token_urlsafe(32), now.isoformat()))
    db.commit()
    return db.fetchone(f'SELECT unsubscribed, token FROM email_update_preferences WHERE email={db.param}', (email,))


def token_email(db, token):
    row = db.fetchone(f'SELECT email FROM email_update_preferences WHERE token={db.param}', (token,))
    if not row:
        raise HTTPException(404, 'Invalid unsubscribe link')
    return row[0]


@router.get('/v1/email-updates/unsubscribe', response_class=HTMLResponse)
def unsubscribe_confirmation(token: str, db: Database = Depends(get_db)):
    token_email(db, token)
    return HTMLResponse('<h1>Email updates</h1><form method="post"><button type="submit">'
                        'Unsubscribe from email updates</button></form>',
                        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@router.post('/v1/email-updates/unsubscribe', response_class=HTMLResponse)
def unsubscribe(token: str, db: Database = Depends(get_db)):
    email = token_email(db, token)
    db.execute(f'UPDATE email_update_preferences SET unsubscribed=1, updated_at={db.param} WHERE email={db.param}',
               (datetime.now(timezone.utc).isoformat(), email))
    db.commit()
    return HTMLResponse('<h1>You have been unsubscribed from email updates.</h1>',
                        headers={'Cache-Control': 'no-store'})


def current_pairs(db, subject):
    # Use precisely the same preferences/value/sent-offer rules as the closet route.
    from .assistant_reads import marketplace_matches
    from .main import _listing_matches_viewer_preferences, _trade_match_tolerance, _sent_offer_match_pairs
    pairs = {}
    offset = 0
    while True:
        sources = db.list_owner_listings(subject, limit=200, offset=offset)
        for source in sources:
            if str(source.get('status', '')).lower() != 'active':
                continue
            page_offset = 0
            while True:
                page = marketplace_matches(source['listing_id'], subject=subject, db=db, limit=100,
                    offset=page_offset, matches_preferences=_listing_matches_viewer_preferences,
                    tolerance_for=_trade_match_tolerance, sent_pairs=_sent_offer_match_pairs, hydrate=lambda x: x)
                for target in page['items']:
                    pairs[(source['listing_id'], target['listing_id'])] = (source, target)
                if not page['has_more']:
                    break
                page_offset = page['next_offset']
        if len(sources) < 200:
            break
        offset += len(sources)
    return pairs


def observe(db, subject, pairs, now, window_end=None):
    baseline = db.fetchone(f'SELECT created_at FROM match_feed_baselines WHERE owner_subject={db.param}', (subject,))
    # Seed legacy matches outside the first digest window, rather than inventing their age.
    first_seen = now if baseline else now - timedelta(days=2)
    for source, target in pairs:
        db.execute(f'''INSERT INTO match_feed_observations
            (owner_subject, source_id, target_id, first_seen_at)
            VALUES ({db.param}, {db.param}, {db.param}, {db.param})
            ON CONFLICT (owner_subject, source_id, target_id) DO NOTHING''',
            (subject, source, target, first_seen.isoformat()))
    db.execute(f'''INSERT INTO match_feed_baselines (owner_subject, created_at)
        VALUES ({db.param}, {db.param}) ON CONFLICT (owner_subject) DO NOTHING''', (subject, now.isoformat()))
    db.commit()
    rows = db.fetchall(f'''SELECT source_id, target_id, first_seen_at FROM match_feed_observations
        WHERE owner_subject={db.param}''', (subject,))
    window_end = window_end or now
    return [pairs[(s, t)] for s, t, date in rows
            if (s, t) in pairs and window_end - timedelta(hours=24) < datetime.fromisoformat(date) <= window_end]


def compose(settings, email, token, matches):
    url = settings.public_api_url.rstrip('/') + '/v1/email-updates/unsubscribe?' + urlencode({'token': token})
    message = EmailMessage()
    message['From'] = settings.notification_from_email or settings.ses_from_email
    message['To'] = email
    message['Subject'] = 'Your daily Jouft matches'
    message['List-Unsubscribe'] = '<' + url + '>'
    message['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
    text = ['New matches first observed for your listings in the past 24 hours:', '']
    html = ['<h1>Your new marketplace matches</h1><p>First observed in the past 24 hours.</p><ul>']
    seen = set()
    for source, target in matches:
        key = (source['listing_id'], target['listing_id'])
        if key in seen:
            continue
        seen.add(key)
        link = settings.public_app_url.rstrip('/') + '/?tab=market&' + urlencode({'listing': target['listing_id']})
        label = f"{target.get('title') or 'Marketplace item'} — matches your {source.get('title') or 'listing'}"
        text.append(label + '\n' + link)
        html.append('<li><a href="' + escape(link, quote=True) + '">' + escape(label) + '</a></li>')
    text.append('\nUnsubscribe from email updates: ' + url)
    html.append('</ul><p><a href="' + escape(url, quote=True) + '">Unsubscribe from email updates</a></p>')
    message.set_content('\n'.join(text))
    message.add_alternative(''.join(html), subtype='html')
    return message


def send_ses(settings, message):
    import boto3
    from botocore.exceptions import ClientError
    session = boto3.session.Session(region_name=settings.ses_region or settings.aws_region,
        aws_access_key_id=settings.ses_access_key_id, aws_secret_access_key=settings.ses_secret_access_key,
        aws_session_token=settings.ses_session_token)
    v2 = session.client('sesv2', endpoint_url=settings.ses_endpoint_url or None)
    try:
        v2.get_suppressed_destination(EmailAddress=message['To'])
        return 'suppressed'
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'NotFoundException':
            raise
    response = session.client('ses', endpoint_url=settings.ses_endpoint_url or None).send_raw_email(
        Source=message['From'], Destinations=[message['To']], RawMessage={'Data': message.as_bytes()})
    return 'sent' if response.get('MessageId') else 'unknown'


def tick(settings, *, now=None, deliver=send_ses):
    if not settings.daily_match_feed_enabled:
        return {'disabled': True}
    now = now or datetime.now(timezone.utc)
    cutoff = now.replace(hour=settings.daily_match_feed_utc_hour, minute=0, second=0, microsecond=0)
    db = Database(settings.database_url)
    db.verify_schema()
    counts = {'sent': 0, 'skipped': 0, 'failed': 0}
    try:
        # Group duplicate profile addresses into one digest, never one email per listing.
        recipients = {}
        for subject, email in db.fetchall('SELECT owner_subject, email FROM user_profiles'):
            if email and str(email).strip():
                recipients.setdefault(email.strip().lower(), []).append(subject)
        for email, subjects in recipients.items():
            claimed_day = None
            try:
                pref = preference(db, email, now)
                if pref[0]:
                    counts['skipped'] += 1
                    continue
                matches = []
                for subject in subjects:
                    matches.extend(observe(db, subject, current_pairs(db, subject), now, window_end=cutoff))
                if not matches or now.hour < settings.daily_match_feed_utc_hour:
                    continue
                day = now.date().isoformat()
                # Claim before contacting SES. Ambiguous send failures are not retried
                # automatically, avoiding duplicate messages after a crash/timeout.
                claim = secrets.token_hex(16)
                db.execute(f'''INSERT INTO match_feed_deliveries (email, day, status, created_at)
                    VALUES ({db.param}, {db.param}, {db.param}, {db.param})
                    ON CONFLICT (email, day) DO NOTHING''', (email, day, claim, now.isoformat()))
                db.commit()
                state = db.fetchone(f'SELECT status FROM match_feed_deliveries WHERE email={db.param} AND day={db.param}', (email, day))
                if state[0] != claim:
                    continue
                claimed_day = day
                if preference(db, email, now)[0]:
                    status = 'unsubscribed'
                else:
                    status = deliver(settings, compose(settings, email, pref[1], matches))
                db.execute(f'UPDATE match_feed_deliveries SET status={db.param} WHERE email={db.param} AND day={db.param}',
                           (status, email, day))
                db.commit()
                counts['sent' if status == 'sent' else 'skipped'] += 1
            except Exception:
                if db._pg is not None:
                    db._pg.rollback()
                elif db._sqlite_conn is not None:
                    db._sqlite_conn.rollback()
                if claimed_day:
                    db.execute(f'UPDATE match_feed_deliveries SET status={db.param} WHERE email={db.param} AND day={db.param}',
                               ('unknown', email, claimed_day))
                    db.commit()
                # Do not log recipient addresses, tokens, credentials or message bodies.
                counts['failed'] += 1
        return counts
    finally:
        db.close()
