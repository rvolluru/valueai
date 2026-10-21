import pytest
from fastapi import HTTPException
from app.assistant_reads import matching_preferences, trade_status


class DB:
    def get_user_profile_quiz(self, subject):
        assert subject == 'me'
        return dict(tops_size='M', shoes_size='US 10', category_preferences=['shoes'],
                    email='private-email', shipping_phone='private-phone', payment_methods=['secret'])
    def list_trade_offers_for_subject(self, subject, limit):
        return [self.get_trade_offer_by_id('mine'), self.get_trade_offer_by_id('foreign')]
    def get_trade_offer_by_id(self, key):
        return dict(offer_id=key, target_listing_id='listing', status='pending',
                    from_subject='me' if key == 'mine' else 'other', to_subject='seller',
                    from_receive_address={'address': 'secret'}, message='private message')
    def get_listing_by_id(self, key): return dict(title='Coat', owner_subject='seller', email='secret')
    def list_shipments_for_offer(self, key):
        assert key == 'mine'
        return [dict(from_subject='me', to_subject='seller', carrier='UPS', status='shipped',
                     tracking_status='IN_TRANSIT', tracking_eta='2026-10-23', to_address_line1='secret'),
                dict(from_subject='foreign', to_subject='seller', carrier='PRIVATE')]


def test_preference_read_excludes_personal_and_billing_fields():
    prefs = matching_preferences(subject='me', db=DB())
    assert prefs['shoes_size'] == 'US 10'
    assert set(prefs) == {'category_preferences', 'tops_size', 'dresses_size', 'bottoms_size', 'shoes_size'}


def test_pending_read_filters_before_paging_and_never_includes_foreign_offers():
    class Mixed(DB):
        def list_trade_offers_for_subject(self, subject, limit):
            assert limit == 50
            return [{**self.get_trade_offer_by_id('mine'), 'offer_id': status, 'status': status}
                    for status in ('pending', 'accepted', 'declined', 'proposed', 'completed')] + [self.get_trade_offer_by_id('foreign')]
    rows = trade_status(subject='me', db=Mixed(), pending_only=True)
    assert [row['offer_id'] for row in rows] == ['pending']


@pytest.mark.parametrize('shipping', [False, True])
def test_status_projection_checks_participants_and_drops_sensitive_fields(shipping):
    rows = trade_status(subject='me', db=DB(), shipping=shipping)
    assert len(rows) == 1 and rows[0]['offer_id'] == 'mine'
    assert 'secret' not in str(rows) and 'PRIVATE' not in str(rows)
    with pytest.raises(HTTPException) as error:
        trade_status(subject='me', db=DB(), shipping=shipping, offer_id='foreign')
    assert error.value.status_code == 404
