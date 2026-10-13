import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createMobileApiClient } from './apiClient.js';

test('mobile loads eligible-item pages and submits the receiver selection', async () => {
  const original = global.fetch;
  try {
    const requests = [];
    global.fetch = async (url, options) => {
      requests.push({ url, options });
      return { ok: true, status: 200, json: async () => options.method === 'POST' ? { status: 'proposed' }
        : requests.length === 1 ? { items: [{ listing_id: 'one' }], has_more: true, next_offset: 1 }
        : { items: [{ listing_id: 'two' }], has_more: false } };
    };
    const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
    assert.equal((await client.proposalCandidates('offer')).items.length, 2);
    await client.proposeOffer('offer', ['two']);
    assert.deepEqual(JSON.parse(requests[2].options.body), { status: 'proposed', proposed_listing_ids: ['two'] });
  } finally { global.fetch = original; }
});

test('Active and Closed fall back only when an older API rejects grouping filters', async () => {
  const original = global.fetch;
  try {
    const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
    for (const [group, expected] of [['active', ['accepted', 'pending']], ['done', ['declined', 'finished']]]) {
      const calls = [];
      global.fetch = async (url) => {
        calls.push(url);
        return calls.length === 1
          ? { ok: false, status: 400, json: async () => ({ detail: 'Invalid status filter' }) }
          : { ok: true, status: 200, json: async () => ({ actor: { subject: 'owner' }, items: ['accepted', 'declined', 'finished', 'pending'].map(status => ({ status })) }) };
      };
      const payload = await client.incomingOffers(group);
      assert.deepEqual(payload.items.map(offer => offer.status), expected);
      assert.equal(payload.actor.subject, 'owner');
      assert.ok(calls[1].endsWith('status=all&limit=200'));
    }
    let calls = 0;
    global.fetch = async () => { calls++; return { ok: false, status: 401, json: async () => ({ detail: 'Unauthorized' }) }; };
    await assert.rejects(client.incomingOffers('active'), /Unauthorized/);
    assert.equal(calls, 1);
  } finally {
    global.fetch = original;
  }
});
