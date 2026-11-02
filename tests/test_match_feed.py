from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import match_feed as feed
from app.auth import get_request_principal
from app.db import Database
from app.deps import get_db


def setup(tmp_path):
    settings = SimpleNamespace(database_url=f'sqlite:///{tmp_path / "feed.db"}',
        daily_match_feed_enabled=True, daily_match_feed_utc_hour=14,
        notification_from_email='notifications@example.com', ses_from_email=None,
        public_api_url='https://api.example.com', public_app_url='https://example.com')
    db = Database(settings.database_url)
    db.initialize()
    db.execute("INSERT INTO user_profiles (owner_subject, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
               ('owner', 'User@example.com', '2026-11-01', '2026-11-01'))
    db.commit()
    return settings, db


def pair(source='mine', target='new'):
    return {(source, target): ({'listing_id': source, 'title': '<My shoes>'},
                              {'listing_id': target, 'title': '<New shoes>'})}


def test_first_run_baselines_old_matches_and_only_new_current_pairs_qualify(tmp_path):
    _, db = setup(tmp_path)
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    assert feed.observe(db, 'owner', pair(), now) == []
    new = pair(target='second')
    assert len(feed.observe(db, 'owner', {**pair(), **new}, now + timedelta(hours=1))) == 1
    assert feed.observe(db, 'owner', {}, now + timedelta(hours=2)) == []
    assert feed.observe(db, 'owner', new, now + timedelta(days=2)) == []


def test_send_once_per_day_and_honor_unsubscribe(tmp_path, monkeypatch):
    settings, db = setup(tmp_path)
    now = datetime(2026, 11, 2, 13, tzinfo=timezone.utc)
    feed.observe(db, 'owner', {}, now - timedelta(days=1))
    monkeypatch.setattr(feed, 'current_pairs', lambda *args: pair())
    sent = []
    def deliver(settings, message):
        sent.append(message)
        return 'sent'
    assert feed.tick(settings, now=now, deliver=deliver)['sent'] == 0
    assert feed.tick(settings, now=now + timedelta(hours=1), deliver=deliver)['sent'] == 1
    assert feed.tick(settings, now=now + timedelta(hours=2), deliver=deliver)['sent'] == 0
    assert len(sent) == 1
    assert sent[0]['To'] == 'user@example.com'
    assert 'List-Unsubscribe' in sent[0]
    assert '&lt;New shoes&gt;' in sent[0].get_payload()[1].get_content()
    assert '?tab=market&amp;listing=new' in sent[0].get_payload()[1].get_content()
    db.execute('UPDATE email_update_preferences SET unsubscribed=1')
    db.commit()
    monkeypatch.setattr(feed, 'current_pairs', lambda *args: (_ for _ in ()).throw(AssertionError('Opted out scanned')))
    assert feed.tick(settings, now=now + timedelta(days=1), deliver=deliver)['skipped'] == 1


def test_scheduled_windows_do_not_overlap_and_no_retry_after_ambiguous_send(tmp_path, monkeypatch):
    settings, db = setup(tmp_path)
    now = datetime(2026, 11, 2, 14, 5, tzinfo=timezone.utc)
    feed.observe(db, 'owner', {}, now - timedelta(days=1))
    monkeypatch.setattr(feed, 'current_pairs', lambda *args: pair())
    # First observed after today's cutoff belongs to tomorrow's digest.
    assert feed.tick(settings, now=now, deliver=lambda *a: 'sent')['sent'] == 0
    calls = []
    def ambiguous(*args):
        calls.append(1)
        raise TimeoutError()
    assert feed.tick(settings, now=now + timedelta(days=1), deliver=ambiguous)['failed'] == 1
    assert feed.tick(settings, now=now + timedelta(days=1, minutes=5), deliver=ambiguous)['sent'] == 0
    assert len(calls) == 1


def test_unsubscribe_get_does_not_mutate_post_is_idempotent_and_account_can_resubscribe(tmp_path):
    _, db = setup(tmp_path)
    token = feed.preference(db, 'user@example.com', datetime.now(timezone.utc))[1]
    app = FastAPI()
    app.include_router(feed.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_principal] = lambda: SimpleNamespace(subject='owner')
    client = TestClient(app)
    assert client.get('/v1/me/email-updates').json() == {'subscribed': True}
    assert client.get('/v1/email-updates/unsubscribe', params={'token': token}).status_code == 200
    assert client.get('/v1/me/email-updates').json()['subscribed']
    for _ in range(2):
        assert client.post('/v1/email-updates/unsubscribe', params={'token': token}).status_code == 200
    assert client.get('/v1/me/email-updates').json() == {'subscribed': False}
    assert client.post('/v1/email-updates/unsubscribe', params={'token': 'invalid'}).status_code == 404
    assert client.put('/v1/me/email-updates', json={'subscribed': 'false'}).status_code == 422
    assert client.put('/v1/me/email-updates', json={'subscribed': True}).json()['subscribed']


def test_ses_suppressed_addresses_are_never_sent(tmp_path, monkeypatch):
    import boto3
    settings, _ = setup(tmp_path)
    for name, value in dict(ses_region='us-east-1', aws_region='us-east-1',
                            ses_access_key_id=None, ses_secret_access_key=None,
                            ses_session_token=None, ses_endpoint_url=None).items():
        setattr(settings, name, value)
    class SES:
        def get_suppressed_destination(self, **kwargs):
            return {'SuppressedDestination': {'EmailAddress': kwargs['EmailAddress']}}
        def send_raw_email(self, **kwargs):
            raise AssertionError('Suppressed recipient must not be mailed')
    monkeypatch.setattr(boto3.session, 'Session', lambda **kwargs: SimpleNamespace(client=lambda *a, **kw: SES()))
    message = feed.compose(settings, 'user@example.com', 'token', list(pair().values()))
    assert feed.send_ses(settings, message) == 'suppressed'


def test_disabled_digest_does_not_open_database():
    assert feed.tick(SimpleNamespace(daily_match_feed_enabled=False)) == {'disabled': True}
