import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
test('data deletion instructions are public and linked from privacy', () => {
  assert.ok(app.indexOf("=== '/data-deletion'") < app.indexOf('if (CLERK_ENABLED) return'));
  const privacy = app.slice(app.indexOf('function PrivacyPolicyPage()'), app.indexOf('function DataDeletionPage()'));
  assert.match(privacy, /href="\/data-deletion"/);
  const deletion = app.slice(app.indexOf('function DataDeletionPage()'), app.indexOf('function TermsPage()'));
  assert.match(deletion, /mailto:admin@jouft.com\?subject=Jouft%20data%20deletion%20request/);
  assert.match(deletion, /Facebook Login/);
  assert.match(deletion, /does not automatically delete/);
  assert.match(deletion, /verify account ownership/);
});
