from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.db import Database, ActiveTradeRequestError


def offer(key, **overrides):
    return dict(offer_id=key, target_listing_id='target', offered_listing_id='source',
                offered_listing_ids=['source'], from_subject='sender', to_subject='recipient',
                message='', **overrides)


def test_competing_database_connections_cannot_create_duplicate_active_requests(tmp_path):
    url = 'sqlite:///' + str(tmp_path / 'trades.db')
    first, second = Database(url), Database(url)
    first.initialize()
    entered, release = Event(), Event()
    insert = first._insert_trade_offer

    def held_insert(**kwargs):
        entered.set()
        assert release.wait(5)
        return insert(**kwargs)

    first._insert_trade_offer = held_insert
    try:
        with ThreadPoolExecutor() as pool:
            pending = pool.submit(first.create_trade_offer, **offer('first'))
            try:
                assert entered.wait(5)
                with pytest.raises(ActiveTradeRequestError):
                    second.create_trade_offer(**offer('second'))
            finally:
                release.set()
            assert pending.result()['offer_id'] == 'first'
        with pytest.raises(ActiveTradeRequestError):
            second.create_trade_offer(**offer('second'))
        assert len(first.fetchall('SELECT offer_id FROM trade_offers')) == 1
        first.execute("UPDATE trade_offers SET status='declined'")
        first.commit()
        assert second.create_trade_offer(**offer('second'))['offer_id'] == 'second'
    finally:
        first.close()
        second.close()


def test_active_lookup_is_not_limited_to_recent_200_offers():
    db = Database('sqlite:///:memory:')
    db.initialize()
    try:
        db.create_trade_offer(**offer('old-active'))
        for index in range(201):
            db.create_trade_offer(**offer(f'new-{index}', status='declined'))
        assert db.find_active_trade_request('sender', 'target')['offer_id'] == 'old-active'
        with pytest.raises(ActiveTradeRequestError):
            db.create_trade_offer(**offer('duplicate'))
        assert db.find_active_trade_request('other-sender', 'target') is None
    finally:
        db.close()
