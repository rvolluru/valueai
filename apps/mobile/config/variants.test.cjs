const test = require('node:test');
const assert = require('node:assert/strict');
const { buildVariant } = require('./variants.cjs');
const issuer = 'existing-instance.clerk.accounts.dev';
const key = 'pk_test_' + Buffer.from(issuer + '$').toString('base64');
const env = {APP_ENV:'production', JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY:key};
test('production rejects a test key without explicit compatibility settings', () => {
  assert.throws(() => buildVariant({}, env), /live/);
});
test('compatibility requires an exact issuer match', () => {
  assert.throws(() => buildVariant({}, {...env, JOUFT_PRODUCTION_CLERK_ALLOW_TEST_INSTANCE:'true', JOUFT_PRODUCTION_CLERK_ISSUER:'https://other.clerk.accounts.dev'}), /explicit production issuer/);
});
test('existing production instance retains production identity and API', () => {
  const result=buildVariant({}, {...env, JOUFT_PRODUCTION_CLERK_ALLOW_TEST_INSTANCE:'true', JOUFT_PRODUCTION_CLERK_ISSUER:'https://' + issuer});
  assert.equal(result.android.package,'com.jouft.app');
  assert.equal(result.ios.bundleIdentifier,'com.jouft.app');
  assert.equal(result.extra.apiBaseUrl,'https://api.jouft.com');
  assert.equal(result.extra.clerkPublishableKey,key);
});
test('production cannot fall back to a staging key', () => {
  assert.throws(() => buildVariant({}, {APP_ENV:'production', JOUFT_STAGING_CLERK_PUBLISHABLE_KEY:key}), /live/);
});
