import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.access_requests import router
from app.auth import AuthPrincipal, require_admin_user
from app.db import Database
from app.deps import get_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr('app.access_requests.notify_admin', lambda *args: 'sent')
    db = Database(f"sqlite:///{tmp_path / 'requests.db'}"); db.initialize()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client, db, app
    db.close()


def payload(**changes):
    return dict(first_name='Jane', email='jane@example.com', city='Austin', state='TX', clothing_size=['S', 'M'], shoe_size=['7', '7.5'], owned_brands=['Gucci'], wanted_brands=['Prada'], listing_quantity='6-10', typical_value='$150-300', email_consent=True, **changes)


def test_options_and_custom_brand_submission(client):
    http, db, app = client
    options = http.get('/v1/access-request-options').json()
    assert 'Gucci' in options['brands'] and 'Chanel' in options['brands']
    assert options['shoe_sizes'] == ['5', '5.5', '6', '6.5', '7', '7.5', '8', '8.5', '9', '9.5', '10', '10.5', '11', '11.5', '12']
    body = payload(); body['owned_brands'] = ['Independent Designer']
    response = http.post('/v1/access-requests', json=body)
    assert response.status_code == 201, response.text
    assert db.fetchone('SELECT COUNT(*) FROM access_requests')[0] == 1
    assert http.get('/v1/admin/access-requests').status_code in [401, 403]
    app.dependency_overrides[require_admin_user] = lambda: AuthPrincipal('clerk', 'admin', {})
    result = http.get('/v1/admin/access-requests').json()
    assert result['items'][0]['owned_brands'] == ['Independent Designer']
    assert result['items'][0]['clothing_size'] == ['S', 'M']
    assert result['items'][0]['shoe_size'] == ['7', '7.5']
    assert result['items'][0]['consent_at'] and result['items'][0]['email_consent']


@pytest.mark.parametrize('field,value', [('email', 'invalid'), ('first_name', ' '), ('city', ' '), ('state', 'ZZ'), ('clothing_size', 'XXXS'), ('shoe_size', '12.5'), ('listing_quantity', '50'), ('typical_value', 'free'), ('email_consent', False), ('owned_brands', []), ('wanted_brands', ['A','B','C','D','E','F']), ('owned_brands', ['Gucci', 'gucci']), ('owned_brands', [' '])])
def test_invalid_requests_not_stored(client, field, value):
    http, db, _ = client
    body = payload(); body[field] = value
    assert http.post('/v1/access-requests', json=body).status_code == 422
    assert db.fetchone('SELECT COUNT(*) FROM access_requests')[0] == 0


def test_duplicate_email_updates_and_rate_limits(client):
    http, db, _ = client
    body = payload()
    assert http.post('/v1/access-requests', json=body).status_code == 201
    body.update(first_name='Janet', email='JANE@example.com')
    assert http.post('/v1/access-requests', json=body).status_code == 201
    assert db.fetchone('SELECT COUNT(*) FROM access_requests')[0] == 1
    for _ in range(3): assert http.post('/v1/access-requests', json=body).status_code == 201
    assert http.post('/v1/access-requests', json=body).status_code == 429


def test_honeypot_rejected(client):
    http, db, _ = client
    body = payload(); body['website'] = 'spam'
    assert http.post('/v1/access-requests', json=body).status_code == 400
    assert db.fetchone('SELECT COUNT(*) FROM access_requests')[0] == 0


@pytest.mark.parametrize('field,value', [('clothing_size', []), ('shoe_size', []), ('clothing_size', ['S', 'custom']), ('shoe_size', ['7', '12.5']), ('shoe_size', ['7', '7'])])
def test_multiselect_rejects_freeform_empty_or_duplicate_sizes(client, field, value):
    http, db, _ = client
    body = payload(); body[field] = value
    assert http.post('/v1/access-requests', json=body).status_code == 422
    assert db.fetchone('SELECT COUNT(*) FROM access_requests')[0] == 0



def test_csv_exports_all_fields_and_timestamps(client):
    import csv, io
    http, db, app = client
    assert http.get('/v1/admin/access-requests/export.csv').status_code in [401, 403]
    body = payload(); body['first_name'] = '=DANGER()'
    assert http.post('/v1/access-requests', json=body).status_code == 201
    app.dependency_overrides[require_admin_user] = lambda: AuthPrincipal('clerk', 'admin', {})
    response = http.get('/v1/admin/access-requests/export.csv')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]['first_name'] == "'=DANGER()"
    assert rows[0]['submitted_at_utc'] and rows[0]['last_submitted_at_utc']
    assert rows[0]['clothing_size'] == 'S; M'
    assert rows[0]['email_consent'] == 'True'


def test_notification_queued_only_for_accepted_submission(client, monkeypatch):
    http, db, _ = client
    calls = []
    monkeypatch.setattr('app.access_requests.notify_admin', lambda *args: calls.append(args))
    assert http.post('/v1/access-requests', json=payload()).status_code == 201
    assert len(calls) == 1 and calls[0][1]['email'] == 'jane@example.com'
    assert calls[0][2]
    bad = payload(); bad['email_consent'] = False
    assert http.post('/v1/access-requests', json=bad).status_code == 422
    assert len(calls) == 1


def test_admin_notification_email_recipient_and_content(monkeypatch):
    from app.access_requests import notify_admin
    from app.settings import Settings
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self): pass
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr('app.access_requests.smtplib.SMTP', SMTP)
    settings = Settings(_env_file=None, email_provider='smtp', smtp_host='test', smtp_username=None, notification_from_email='notifications@jouft.com')
    assert notify_admin(settings, payload(), '2026-11-23T18:00:00+00:00') == 'sent'
    assert sent[0]['To'] == 'admin@jouft.com'
    content = sent[0].get_content()
    assert '2026-11-23T18:00:00+00:00' in content
    assert 'jane@example.com' in content and 'Gucci' in content


def test_notification_failure_is_logged_without_raising(monkeypatch):
    from app.access_requests import notify_admin
    from app.settings import Settings
    def fail(*args, **kwargs): raise RuntimeError('provider unavailable')
    monkeypatch.setattr('app.access_requests.smtplib.SMTP', fail)
    settings = Settings(_env_file=None, email_provider='smtp', smtp_host='test')
    assert notify_admin(settings, payload(), '2026-11-23T18:00:00+00:00') == 'failed'
