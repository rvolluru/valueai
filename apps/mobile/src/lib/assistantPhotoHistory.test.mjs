import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('historical assistant photos resolve against the configured API base', () => {
  const source = readFileSync(new URL('../components/AssistantConversation.jsx', import.meta.url), 'utf8');
  const app = readFileSync(new URL('../../App.js', import.meta.url), 'utf8');
  assert.match(source, /uri: new URL\(photo\.url, apiBaseUrl\)\.href/);
  assert.match(app, /<AssistantConversation[^>]+apiBaseUrl=\{apiBaseUrl\}/);
  assert.equal(new URL('/v1/images/photo', 'https://api.jouft.com').href, 'https://api.jouft.com/v1/images/photo');
});
