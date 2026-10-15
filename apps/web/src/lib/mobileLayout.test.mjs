import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8');
test('photo role labels take their own row instead of covering Set Hero', () => {
  const badge = css.match(/\.listing-image-role-badge\s*\{([^}]+)\}/)[1];
  assert.match(badge, /position: static/);
  assert.match(badge, /display: block/);
  assert.doesNotMatch(badge, /bottom:/);
});
test('mobile landing header replaces desktop grid columns instead of flex direction', () => {
  const responsive = css.slice(css.indexOf('@media (max-width: 1100px)'));
  const header = responsive.match(/\.auth-hero-topbar\s*\{([^}]+)\}/)[1];
  assert.match(header, /grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.doesNotMatch(header, /flex-direction/);
});

test('profile layout can respond to mobile widths instead of an inline desktop grid', () => {
  const app = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
  assert.match(app, /className="profile-settings-layout"/);
  assert.doesNotMatch(app, /gridTemplateColumns: '220px 1fr'/);
  const mobile = css.slice(css.lastIndexOf('@media (max-width: 760px)'));
  assert.match(mobile, /\.profile-settings-layout[^{}]*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(mobile, /\.inbox-editorial-actions\s*\{[^}]*flex-direction: column/);
  assert.match(mobile, /\.listing-review-layout/);
});
