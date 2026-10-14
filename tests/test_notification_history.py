import pytest
from app.db import Database
from app.auth import AuthPrincipal
from app.main import delete_notification


@pytest.fixture
def notifications_db(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'notifications.db'}")
    db.initialize()
    yield db
    db._sqlite_conn.close()


def add(db, notification_id, owner='owner'):
    db.create_user_notification(notification_id=notification_id, owner_subject=owner,
                                actor_subject=None, type='trade-update', title='Trade update',
                                body='Your trade was updated.', entity_id='trade', action_tab='inbox')


def test_history_pages_all_notifications_and_is_owner_scoped(notifications_db):
    db = notifications_db
    for index in range(123): add(db, f'notice-{index:03}')
    add(db, 'other-user-notice', 'other')
    pages = [db.list_user_notifications('owner', limit=50, offset=offset) for offset in (0, 50, 100)]
    assert [len(page) for page in pages] == [50, 50, 23]
    assert len({item['notification_id'] for page in pages for item in page}) == 123
    assert all(item['owner_subject'] == 'owner' for page in pages for item in page)


def test_read_state_persists_without_deleting_history(notifications_db):
    db = notifications_db
    add(db, 'notice')
    assert not db.mark_user_notification_read('other', 'notice')
    assert db.mark_user_notification_read('owner', 'notice')
    first = db.list_user_notifications('owner')[0]['read_at']
    assert first
    assert db.mark_user_notification_read('owner', 'notice')
    assert db.list_user_notifications('owner')[0]['read_at'] == first


def test_legacy_delivery_acknowledgement_retains_history(notifications_db):
    db = notifications_db
    add(db, 'notice')
    principal = AuthPrincipal(auth_type='api_key', subject='owner', claims={})
    delete_notification('notice', principal, db)
    history = db.list_user_notifications('owner')
    assert len(history) == 1
    assert history[0]['read_at']
