import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createApiClient } from '../src/index.js';

test('eligible-item browser loads every page', async () => {
  const urls = [];
  const client = createApiClient({ apiBaseUrl: 'https://example.test', fetchImpl: async (url) => {
    urls.push(url);
    return { ok: true, status: 200, json: async () => urls.length === 1
      ? { items: [{ listing_id: 'one' }], has_more: true, next_offset: 1 }
      : { items: [{ listing_id: 'two' }], has_more: false } };
  }});
  const result = await client.proposalCandidates('offer', 100);
  assert.deepEqual(result.items.map((item) => item.listing_id), ['one', 'two']);
  assert.ok(urls[1].endsWith('offset=1'));
});
