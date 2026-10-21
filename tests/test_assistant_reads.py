import pytest
from fastapi import HTTPException
from app.assistant_reads import MatchRead, grouped_matches, marketplace_matches


@pytest.mark.parametrize('owner,status,allowed', [
    ('me', 'Review', True), ('other', 'Active', True), ('other', 'Review', False),
    ('other', 'Deleted', False),
])
def test_saved_read_revalidates_visibility(owner, status, allowed):
    from app.assistant_reads import saved_listing
    class DB:
        def get_listing_by_id(self, key):
            return dict(listing_id=key, owner_subject=owner, status=status)
    if allowed:
        assert saved_listing('item', subject='me', db=DB())['listing_id'] == 'item'
    else:
        with pytest.raises(HTTPException) as error:
            saved_listing('item', subject='me', db=DB())
        assert error.value.status_code == 404


def test_shared_search_and_card_contracts():
    from app.assistant_reads import search_marketplace, listing_card
    item = dict(listing_id='a', brand='CHANEL', title='Black loafers', size='US 10',
                image='one', images=['one', 'two', 'bad'], owner_subject='secret', analysis={'private': True})
    result = search_marketplace([item, dict(listing_id='b', brand='Other')], [' chanel ', 'LOAFERS'])
    assert result['count'] == 1 and result['items'] == [item]
    assert search_marketplace([item], ['jacket'])['count'] == 0
    card = listing_card(item, public_image=lambda value: None if value == 'bad' else value)
    assert card['images'] == ['one', 'two']
    assert 'owner_subject' not in card and 'analysis' not in card


@pytest.mark.parametrize('scope,source', [('one', None), ('all_eligible', 'a'), ('unknown', None)])
def test_scope_is_explicit(scope, source):
    with pytest.raises(ValueError):
        MatchRead(scope=scope, source_listing_id=source)


@pytest.mark.parametrize('scope,expected', [('one', ['a']), ('all_eligible', ['a', 'b'])])
def test_match_scope_preserves_source_target_pairs(scope, expected):
    owned = [dict(listing_id=i, status='Active', estimated_value=100, title=i) for i in ['a', 'b']]
    owned.append(dict(listing_id='draft', status='Review', estimated_value=100))
    calls = []
    def read(source, limit):
        calls.append(source)
        return dict(count=1, items=[dict(listing_id='same-target')])
    groups = grouped_matches(MatchRead(scope=scope, source_listing_id='a' if scope == 'one' else None),
        owned_listings=owned, read_source=read)
    assert calls == expected
    assert [g['source_listing_id'] for g in groups] == expected
    assert all(g['items'][0]['listing_id'] == 'same-target' for g in groups)
    with pytest.raises(HTTPException):
        grouped_matches(MatchRead(scope='one', source_listing_id='foreign'), owned_listings=owned, read_source=read)


def test_matching_policy_and_pagination_are_unchanged():
    class DB:
        def get_listing_by_id(self, key):
            return dict(owner_subject='me', status='Active', estimated_value=100)
        def get_user_profile_quiz(self, subject): return {}
        def list_recent_listings(self, **kwargs):
            assert kwargs['active_only']
            return [dict(listing_id=i, owner_subject=owner, estimated_value=value)
                for i, owner, value in [('own', 'me', 100), ('sent', 'other', 100),
                    ('wrong-preference', 'other', 100), ('expensive', 'other', 200),
                    ('zero', 'other', 0), ('first', 'other', 100), ('second', 'other', 105)]]
    def read(subject='me', offset=0):
        return marketplace_matches('source', subject=subject, db=DB(), limit=1, offset=offset,
            matches_preferences=lambda t, p: t['listing_id'] != 'wrong-preference',
            tolerance_for=lambda value: (10, None), sent_pairs=lambda db, s: {('sent', 'source')},
            hydrate=lambda item: {**item, 'hydrated': True})
    first = read()
    assert first['count'] == 2 and first['next_offset'] == 1
    assert first['items'][0]['listing_id'] == 'first'
    assert first['items'][0]['hydrated']
    assert read(offset=1)['items'][0]['listing_id'] == 'second'
    with pytest.raises(HTTPException) as error: read(subject='foreign')
    assert error.value.status_code == 404
