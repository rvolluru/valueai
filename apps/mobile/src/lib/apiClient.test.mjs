import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createMobileApiClient } from './apiClient.js';
import { readFileSync } from 'node:fs';

test('mobile implements every API method used by both assistant controllers', () => {
  const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
  for (const file of ['listingAgent.js', 'assistantConversation.js']) {
    const source = readFileSync(new URL(`../../../../packages/app-client/src/${file}`, import.meta.url), 'utf8');
    for (const [, method] of source.matchAll(/client\.([A-Za-z0-9_]+)/g)) {
      assert.equal(typeof client[method], 'function', `${file} requires ${method}`);
    }
  }
});

test('listing agent supports session, review, turns, removal and multipart native photos', async () => {
  const originalFetch = global.fetch;
  const OriginalForm = global.FormData;
  const requests = [];
  try {
    global.FormData = class { entries = []; append(...args) { this.entries.push(args); } };
    global.fetch = async (url, options) => { requests.push({ url, ...options }); return { ok: true, json: async () => ({}) }; };
    const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
    const auth = { bearerToken: 'token' };
    await client.getListingAgentSession('a/b', auth);
    await client.getActiveListingAgentSession(auth);
    await client.startListingAgentSession({ request_id: 'new' }, auth);
    await client.openListingAgentReview({ listing_id: 'listing' }, auth);
    await client.turnWithListingAgent('a/b', { message: 'New' }, auth);
    await client.removeListingAgentPhoto('a/b', { photo_id: 'photo' }, auth);
    await client.uploadListingAgentPhotos({ sessionId: 'a/b', requestId: 'upload', expectedRevision: 2,
      images: [{ uri: 'file:///photo.jpg', fileName: 'photo.jpg', mimeType: 'image/jpeg' }] }, auth);
    assert.deepEqual(requests.map(r => new URL(r.url).pathname), [
      '/v1/listing-agent/sessions/a%2Fb', '/v1/listing-agent/sessions/active',
      '/v1/listing-agent/sessions', '/v1/listing-agent/sessions/review',
      '/v1/listing-agent/sessions/a%2Fb/turns', '/v1/listing-agent/sessions/a%2Fb/photos/remove',
      '/v1/listing-agent/sessions/a%2Fb/photos',
    ]);
    for (const request of requests) assert.equal(request.headers.Authorization, 'Bearer token');
    assert.deepEqual(requests[6].body.entries, [['request_id', 'upload'], ['expected_revision', '2'],
      ['images', { uri: 'file:///photo.jpg', name: 'photo.jpg', type: 'image/jpeg' }]]);
    assert.equal(requests[6].headers['Content-Type'], undefined);
  } finally { global.fetch = originalFetch; global.FormData = OriginalForm; }
});

test('mobile conversation client supports thread and turn endpoints with authentication', async () => {
  const original = global.fetch;
  const requests = [];
  try {
    global.fetch = async (url, options) => { requests.push({ url, ...options }); return { ok: true, json: async () => ({}) }; };
    const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
    const auth = { bearerToken: 'test-token' };
    await client.listAssistantConversations(auth);
    await client.startAssistantConversation({ request_id: 'new' }, auth);
    await client.getAssistantConversation('a/b', auth);
    await client.messageAssistantConversation('a/b', { message: 'hello' }, auth);
    await client.readAssistantConversation('a/b', { action: 'closet' }, auth);
    assert.deepEqual(requests.map(r => [new URL(r.url).pathname, r.method]), [
      ['/v1/assistant-conversations', 'GET'], ['/v1/assistant-conversations', 'POST'],
      ['/v1/assistant-conversations/a%2Fb', 'GET'], ['/v1/assistant-conversations/a%2Fb/messages', 'POST'],
      ['/v1/assistant-conversations/a%2Fb/turns', 'POST'],
    ]);
    for (const request of requests) assert.equal(request.headers.Authorization, 'Bearer test-token');
    assert.deepEqual(JSON.parse(requests[3].body), { message: 'hello' });
  } finally { global.fetch = original; }
});

test('mobile preserves HTTP status for conversation conflict and access handling', async () => {
  const original = global.fetch;
  try {
    global.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: 'Conversation changed' }) });
    const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
    await assert.rejects(client.getAssistantConversation('id'), { status: 409, message: 'Conversation changed' });
  } finally { global.fetch = original; }
});

test('marketplace and closet search carry encoded query through pagination', async () => {
  const original = global.fetch;
  const urls = [];
  try {
    global.fetch = async url => { urls.push(new URL(url)); return { ok: true, json: async () => ({ items: [] }) }; };
    const client = createMobileApiClient({ apiBaseUrl: 'https://example.test' });
    await client.listMarketplace(24, {}, { offset: 24, q: 'Prada & bags' });
    await client.listMyListings(24, {}, { offset: 48, q: 'Prada & bags' });
    for (const url of urls) assert.equal(url.searchParams.get('q'), 'Prada & bags');
    assert.equal(urls[0].searchParams.get('offset'), '24');
    assert.equal(urls[1].searchParams.get('offset'), '48');
    assert.equal(urls[1].searchParams.get('mine'), 'true');
  } finally { global.fetch = original; }
});

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
