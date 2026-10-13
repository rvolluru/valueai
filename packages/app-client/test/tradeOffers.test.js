import assert from 'node:assert/strict';
import { test } from 'node:test';
import { tradeOfferGroup } from '../src/tradeOffers.js';

test('only declined and finished offers belong to Done', () => {
  for (const status of ['declined', 'completed', 'finished', ' DECLINED ']) {
    assert.equal(tradeOfferGroup({ status }), 'done');
  }
  for (const status of ['requested', 'proposed', 'pending', 'accepted', 'countered', 'cancelled', 'shipped', 'future_status', '', null]) {
    assert.equal(tradeOfferGroup({ status }), 'active');
  }
});
