import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('web and mobile publication cards do not repeat the assistant transcript reply', () => {
  for (const path of ['../components/ListingAgentChat.jsx', '../../../mobile/src/components/ListingAgentChat.jsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    const start = source.indexOf("{session.stage === 'published'");
    assert.ok(start >= 0);
    const status = source.slice(start, source.indexOf('Find marketplace matches', start));
    assert.match(status, /Published to Marketplace\./);
    assert.doesNotMatch(status, /session\.messages/);
    assert.doesNotMatch(source, /matching items based on your item/);
    assert.match(source, /Selecting an item only prepares a request; confirmation is required to send\./);
  }
});
