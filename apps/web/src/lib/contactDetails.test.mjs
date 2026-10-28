import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('website uses current contact email and clickable phone', () => {
  const app = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(app, /JOUFTllc@gmail\.com/i);
  assert.match(app, /contact: 'admin@jouft\.com'/);
  assert.match(app, /phone: '\(949\) 354-4133'/);
  assert.match(app, /phoneHref: 'tel:\+19493544133'/);
  assert.match(app, /<a href=\{section.phoneHref\}>\{section.phone\}<\/a>/);
});
