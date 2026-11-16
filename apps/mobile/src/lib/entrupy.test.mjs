import test from 'node:test';
import assert from 'node:assert/strict';
import { createMobileApiClient } from './apiClient.js';

test('Entrupy mobile handoff sends bearer token and encodes listing IDs', async () => {
  const previous = global.fetch;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, ...options });
    return { ok: true, json: async () => ({}) };
  };
  try {
    const api = createMobileApiClient({ apiBaseUrl: 'https://api.example.com' });
    const auth = { bearerToken: 'seller' };
    await api.authorizeEntrupy('a/b', 'raw-request', auth);
    await api.getEntrupyAuthentication('a/b', auth);
    assert.equal(calls[0].url, 'https://api.example.com/v1/listings/a%2Fb/authentication/authorize');
    assert.equal(calls[0].headers.Authorization, 'Bearer seller');
    assert.deepEqual(JSON.parse(calls[0].body), { sdk_authorization_request: 'raw-request' });
    assert.equal(calls[1].method, 'GET');
    assert.equal(calls[1].headers.Authorization, 'Bearer seller');
  } finally { global.fetch = previous; }
});
