import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
const require = createRequire(import.meta.url);
const { buildVariant } = require('../../config/variants.cjs');
const base = require('../../app.json').expo;
const eas = require('../../eas.json');
const staging = { APP_ENV: 'staging', JOUFT_STAGING_API_URL: 'https://staging.example.test', JOUFT_STAGING_CLERK_PUBLISHABLE_KEY: 'pk_test_example' };
const production = { APP_ENV: 'production', JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY: 'pk_live_example' };

test('three profiles map to exactly two separate native identities and schemes', () => {
  assert.deepEqual(Object.keys(eas.build), ['development', 'staging', 'production']);
  for (const env of [{ APP_ENV: 'development' }, staging, production]) {
    const config = buildVariant(base, env);
    const live = env.APP_ENV === 'production';
    assert.equal(config.name, live ? 'JOUFT' : 'Jouft Testing');
    assert.equal(config.ios.bundleIdentifier, live ? 'com.jouft.app' : 'com.jouft.app.dev');
    assert.equal(config.android.package, config.ios.bundleIdentifier);
    assert.equal(config.scheme, config.ios.bundleIdentifier);
    assert.equal(config.extra.appEnvironment, env.APP_ENV);
    assert.equal(config.extra.eas.projectId, base.extra.eas.projectId);
  }
  assert.equal(buildVariant(base, production).version, '1.0.0');
  assert.equal(eas.build.staging.environment, 'preview');
  assert.equal(eas.build.production.environment, 'production');
  assert.equal(eas.submit.staging.ios.ascAppId, '6791465341');
  assert.notEqual(eas.submit.production.ios.ascAppId, '6791465341');
});

test('release config rejects missing keys, mismatched profiles and production API in staging', () => {
  for (const env of [
    { APP_ENV: 'staging' }, { APP_ENV: 'production' },
    { ...staging, JOUFT_STAGING_API_URL: 'https://api.jouft.com' },
    { ...staging, JOUFT_STAGING_API_URL: 'https://jouft.com' },
    { ...staging, JOUFT_STAGING_API_URL: 'http://staging.example.test' },
    { ...staging, JOUFT_STAGING_CLERK_PUBLISHABLE_KEY: 'pk_live_wrong' },
    { ...production, JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY: 'pk_test_wrong' },
    { ...production, EXPO_PUBLIC_API_BASE_URL: 'http://localhost:8000' },
    { ...production, EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY: 'pk_test_wrong' },
    { ...production, EAS_BUILD_PROFILE: 'staging' }, { APP_ENV: 'unknown' },
  ]) assert.throws(() => buildVariant(base, env));
  assert.equal(buildVariant(base, production).extra.apiBaseUrl, 'https://api.jouft.com');
  assert.equal(buildVariant(base, staging).extra.apiBaseUrl, staging.JOUFT_STAGING_API_URL);
  assert.equal(base.extra.clerkPublishableKey, undefined);
});

test('cloud releases regenerate native identities and ignore local dotenv settings', () => {
  const ignore = readFileSync(new URL('../../.easignore', import.meta.url), 'utf8');
  assert.match(ignore, /^ios\/$/m);
  assert.match(ignore, /^android\/$/m);
  const rootIgnore = readFileSync(new URL('../../../../.easignore', import.meta.url), 'utf8');
  assert.match(rootIgnore, /^apps\/mobile\/ios\/$/m);
  assert.match(rootIgnore, /^apps\/mobile\/android\/$/m);
  for (const profile of ['staging', 'production']) {
    assert.equal(eas.build[profile].env.EXPO_NO_DOTENV, '1');
    assert.equal(eas.build[profile].env.APP_ENV, profile);
  }
});

test('production submission refuses to reuse or infer the testing App Store record', () => {
  const script = new URL('../../scripts/submit-production.cjs', import.meta.url);
  const result = spawnSync(process.execPath, [script.pathname, 'ios'], { encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /NEW ascAppId/);
});
