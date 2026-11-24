"""Public signup-interest collection; does not create an account or send email."""
import csv
import io
import smtplib
from email.message import EmailMessage
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .auth import require_admin_user
from .deps import get_db
from .settings import get_settings
from .logging_utils import log_json
from fastapi.responses import Response

router = APIRouter()
STATES = dict(entry.split(':', 1) for entry in 'AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|DE:Delaware|DC:District of Columbia|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|WV:West Virginia|WI:Wisconsin|WY:Wyoming'.split('|'))
CLOTHING = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
SHOES = [str(n / 2).removesuffix('.0') for n in range(10, 25)]
PIECES = ['1-5', '6-10', '11-20', '20+']
VALUES = ['Under $150', '$150-300', '$300-600', '$600-1,000', '$1,000+']
CONSENT = 'I agree to receive emails from Jouft about my access request, invitations, and launch updates.'
BRANDS = sorted([
    'Acne Studios', 'Akris', 'Alexander McQueen', 'ALEXIS', 'Alice + Olivia', 'AllSaints', 'Ami Paris',
    'Anine Bing', 'Aritzia', 'Balenciaga', 'Balmain', 'Bottega Veneta', 'Brunello Cucinelli', 'Burberry',
    'Canada Goose', 'Carolina Herrera', 'Cartier', 'Celine', 'Chanel', 'Chloé', 'Christian Louboutin',
    'Coach', 'Common Projects', 'COS', 'Cult Gaia', 'David Yurman', 'Diane von Furstenberg', 'Dior',
    'Dolce & Gabbana', 'Etro', 'Fendi', 'Ferragamo', 'Frame', 'Free People', 'Ganni', 'Givenchy',
    'Golden Goose', 'Gucci', 'Hermès', 'Isabel Marant', 'Jacquemus', 'Jimmy Choo', 'Johanna Ortiz',
    'Khaite', 'Lafayette 148', 'Loewe', 'Loro Piana', 'Louis Vuitton', 'Lululemon', 'Maje', 'Manolo Blahnik',
    'Marc Jacobs', 'Max Mara', 'MCM', 'Michael Kors', 'Missoni', 'Miu Miu', 'Moncler', 'Moschino',
    'Mulberry', 'Oscar de la Renta', 'Prada', 'Proenza Schouler', 'Rag & Bone', 'Ralph Lauren',
    'Reformation', 'Reiss', 'Rick Owens', 'Roger Vivier', 'Saint Laurent', 'Sandro', 'Self-Portrait',
    'Simone Rocha', 'Staud', 'Stella McCartney', 'Stuart Weitzman', 'Ted Baker', 'The Row', 'Theory',
    'Tiffany & Co.', 'Tod’s', 'Tom Ford', 'Tory Burch', 'Toteme', 'Tumi', 'Ulla Johnson', 'Valentino',
    'Van Cleef & Arpels', 'Veronica Beard', 'Versace', 'Vince', 'Vivienne Westwood', 'Zimmermann',
], key=str.casefold)


class AccessRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    city: str = Field(min_length=1, max_length=100)
    state: str
    clothing_size: list[str] = Field(min_length=1, max_length=6)
    shoe_size: list[str] = Field(min_length=1, max_length=15)
    owned_brands: list[str] = Field(min_length=1, max_length=5)
    wanted_brands: list[str] = Field(min_length=1, max_length=5)
    listing_quantity: str
    typical_value: str
    email_consent: Literal[True]
    website: str = Field(default='', max_length=200)  # Honeypot, not a user field.

    @field_validator('first_name', 'city')
    @classmethod
    def trim_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('This field is required.')
        return value

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+', value):
            raise ValueError('Enter a valid email address.')
        return value

    @field_validator('state', 'listing_quantity', 'typical_value')
    @classmethod
    def valid_option(cls, value, info):
        options = {'state': STATES, 'clothing_size': CLOTHING, 'shoe_size': SHOES, 'listing_quantity': PIECES, 'typical_value': VALUES}
        if value not in options[info.field_name]:
            raise ValueError('Choose one of the available options.')
        return value

    @field_validator('clothing_size', 'shoe_size', mode='before')
    @classmethod
    def legacy_size(cls, value):
        return [value] if isinstance(value, str) else value

    @field_validator('clothing_size', 'shoe_size')
    @classmethod
    def valid_sizes(cls, value, info):
        options = CLOTHING if info.field_name == 'clothing_size' else SHOES
        if len(set(value)) != len(value) or any(size not in options for size in value):
            raise ValueError('Choose distinct sizes from the available options.')
        return value

    @field_validator('owned_brands', 'wanted_brands')
    @classmethod
    def valid_brands(cls, value):
        cleaned = [brand.strip() for brand in value]
        if any(not brand or len(brand) > 80 or any(ord(char) < 32 for char in brand) for brand in cleaned):
            raise ValueError('Brand names must contain 1–80 characters.')
        if len({brand.casefold() for brand in cleaned}) != len(cleaned):
            raise ValueError('Choose up to five distinct brands.')
        return cleaned


@router.get('/v1/access-request-options')
def options():
    return dict(states=STATES, brands=BRANDS, clothing_sizes=CLOTHING, shoe_sizes=SHOES, listing_quantities=PIECES, typical_values=VALUES, consent_text=CONSENT)


@router.post('/v1/access-requests', status_code=201)
def submit(payload: AccessRequest, request: Request, background_tasks: BackgroundTasks, db=Depends(get_db), settings=Depends(get_settings)):
    if payload.website:
        raise HTTPException(400, 'Unable to submit this request.')
    now = datetime.now(timezone.utc).isoformat()
    bucket = now[:13]
    # Persistent per-email throttling survives server restarts and works across workers.
    identity = hashlib.sha256(payload.email.encode()).hexdigest()
    db.execute(f'''INSERT INTO access_request_attempts (identity, bucket, attempts) VALUES ({db.param}, {db.param}, 1)
        ON CONFLICT(identity, bucket) DO UPDATE SET attempts=access_request_attempts.attempts+1''', (identity, bucket))
    db.commit()
    count = db.fetchone(f'SELECT attempts FROM access_request_attempts WHERE identity={db.param} AND bucket={db.param}', (identity, bucket))[0]
    if count > 5:
        raise HTTPException(429, 'Too many requests. Please try again later.')
    data = payload.model_dump(exclude={'website'})
    db.execute(f'''INSERT INTO access_requests (request_id, email, data_json, consent_text, consent_at, created_at, updated_at)
        VALUES ({', '.join([db.param]*7)}) ON CONFLICT(email) DO UPDATE SET
        data_json=excluded.data_json, consent_text=excluded.consent_text, consent_at=excluded.consent_at, updated_at=excluded.updated_at''',
        (str(uuid.uuid4()), payload.email, json.dumps(data), CONSENT, now, now, now))
    db.commit()
    background_tasks.add_task(notify_admin, settings, data, now)
    return {'status': 'received', 'message': 'Thank you for your interest. We’ll contact you about access to Jouft.'}


@router.get('/v1/admin/access-requests')
def list_requests(limit: int = 50, offset: int = 0, principal=Depends(require_admin_user), db=Depends(get_db)):
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    rows = db.fetchall(f'SELECT request_id, data_json, consent_text, consent_at, created_at, updated_at FROM access_requests ORDER BY updated_at DESC, request_id LIMIT {db.param} OFFSET {db.param}', (limit, offset))
    return {'items': [dict(request_id=row[0], **json.loads(row[1]), consent_text=row[2], consent_at=row[3], created_at=row[4], updated_at=row[5]) for row in rows], 'total': db.fetchone('SELECT COUNT(*) FROM access_requests')[0]}


CSV_FIELDS = ['first_name', 'email', 'city', 'state', 'clothing_size', 'shoe_size', 'owned_brands', 'wanted_brands', 'listing_quantity', 'typical_value', 'email_consent']


def display_value(value):
    return '; '.join(map(str, value)) if isinstance(value, list) else str(value if value is not None else '')


def csv_value(value):
    text = display_value(value)
    # Prevent applicant-provided values from being interpreted as spreadsheet formulas.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


@router.get('/v1/admin/access-requests/export.csv')
def export_requests(principal=Depends(require_admin_user), db=Depends(get_db)):
    rows = db.fetchall('SELECT request_id, data_json, consent_text, consent_at, created_at, updated_at FROM access_requests ORDER BY created_at DESC, request_id')
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['request_id', 'submitted_at_utc', 'last_submitted_at_utc', *CSV_FIELDS, 'consent_text', 'consent_at_utc'])
    for row in rows:
        data = json.loads(row[1])
        writer.writerow([csv_value(value) for value in [row[0], row[4], row[5], *[data.get(key) for key in CSV_FIELDS], row[2], row[3]]])
    return Response(content=('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="jouft-access-requests.csv"', 'Cache-Control': 'no-store'})


def notify_admin(settings, data, submitted_at):
    sender = settings.notification_from_email or settings.ses_from_email or settings.smtp_from_email
    if not sender:
        log_json('access_request_admin_email', status='skipped_not_configured')
        return 'skipped_not_configured'
    message = EmailMessage()
    message['From'] = sender
    message['To'] = 'admin@jouft.com'
    message['Subject'] = 'New Jouft waiting list request'
    labels = ['First name', 'Email', 'City', 'State', 'Clothing sizes', 'Shoe sizes (US)', 'Brands owned', 'Brands wanted', 'Pieces to list', 'Typical value', 'Email consent']
    body = ['A waiting list request was submitted.', f'Submitted at (UTC): {submitted_at}', '']
    body.extend(f'{label}: {display_value(data.get(key))}' for label, key in zip(labels, CSV_FIELDS))
    body.extend(['', f'Review requests: {settings.public_app_url.rstrip("/")}/?tab=admin', '', f'Consent: {CONSENT}'])
    message.set_content('\n'.join(body))
    def smtp_send():
        if not settings.smtp_host:
            raise RuntimeError('SMTP not configured')
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
            if settings.smtp_use_tls: client.starttls()
            if settings.smtp_username: client.login(settings.smtp_username, settings.smtp_password or '')
            client.send_message(message)
    try:
        provider = str(settings.email_provider or 'auto').lower()
        if provider == 'smtp':
            smtp_send()
        else:
            try:
                import boto3
                session = boto3.session.Session(region_name=settings.ses_region or settings.aws_region or 'us-east-1', aws_access_key_id=settings.ses_access_key_id or None, aws_secret_access_key=settings.ses_secret_access_key or None, aws_session_token=settings.ses_session_token or None)
                session.client('ses', endpoint_url=settings.ses_endpoint_url or None).send_raw_email(Source=sender, Destinations=['admin@jouft.com'], RawMessage={'Data': message.as_bytes()})
            except Exception:
                if provider != 'auto' or not settings.smtp_host: raise
                smtp_send()
        log_json('access_request_admin_email', status='sent')
        return 'sent'
    except Exception as error:
        # Persisted requests remain available even if notification delivery fails.
        log_json('access_request_admin_email', status='failed', error=type(error).__name__)
        return 'failed'
