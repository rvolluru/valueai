import inspect
import pytest
from app.db import Database
from app.usernames import UsernameError, default_username


def save(db, subject, **changes):
    params = {key: None for key, param in inspect.signature(db.upsert_user_profile_quiz).parameters.items() if param.default is inspect.Parameter.empty}
    params.update(owner_subject=subject, first_name='Jane', last_name='Doe', category_preferences=[], style_descriptors=[], jouft_goals=[], shipping_addresses=[], payment_methods=[])
    params.update(changes)
    return db.upsert_user_profile_quiz(**params)


@pytest.fixture
def db(tmp_path):
    connection = Database(f"sqlite:///{tmp_path / 'handles.db'}")
    connection.initialize()
    yield connection
    connection.close()


def test_defaults_unique_and_preserves_custom_username(db):
    assert save(db, 'a')['username'] == 'jane_doe'
    assert save(db, 'b')['username'] == 'jane_doe_2'
    assert save(db, 'a', username='@My_Closet')['username'] == 'my_closet'
    assert save(db, 'a', first_name='Janet')['username'] == 'my_closet'
    assert db.get_user_profile_quiz('a')['username'] == 'my_closet'


def test_invalid_and_duplicate_handles_leave_profile_unchanged(db):
    save(db, 'a', username='style')
    save(db, 'b', username='closet')
    with pytest.raises(UsernameError, match='already taken'):
        save(db, 'b', username='STYLE')
    with pytest.raises(UsernameError, match='letters'):
        save(db, 'b', username='bad handle!')
    assert db.get_user_profile_quiz('b')['username'] == 'closet'
    assert save(db, 'b', username='new_style')['username'] == 'new_style'


def test_backfill_existing_profiles(db):
    from app.migrations import _profile_usernames
    save(db, 'a'); save(db, 'b')
    db.execute('UPDATE user_profiles SET username = NULL'); db.commit()
    _profile_usernames(db)
    assert {db.get_user_profile_quiz(x)['username'] for x in ['a', 'b']} == {'jane_doe', 'jane_doe_2'}
    _profile_usernames(db)
    assert db.get_user_profile_quiz('a')['username']


def test_listing_hydration_uses_latest_handle(db):
    from app.main import _hydrate_listing_owner_name
    save(db, 'a', username='my_closet')
    listing = {'owner_subject': 'a', 'owner_name': 'Jane Doe'}
    assert _hydrate_listing_owner_name(db, listing)['owner_name'] == 'my_closet'
    save(db, 'a', username='new_closet')
    assert _hydrate_listing_owner_name(db, listing)['owner_name'] == 'new_closet'


def test_non_ascii_default():
    assert default_username('José', 'De León') == 'jose_de_leon'
    assert default_username('', '') == 'member'
