import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { nextGalleryIndex } from './galleryPaging.mjs';

test('Next advances exactly one photo, not to the last photo', () => {
  assert.equal(nextGalleryIndex(0, 1, 6), 1);
  assert.equal(nextGalleryIndex(1, 1, 6), 2);
  assert.equal(nextGalleryIndex(4, 1, 6), 5);
  assert.equal(nextGalleryIndex(5, 1, 6), 5);
  assert.equal(nextGalleryIndex(2, -1, 6), 1);
});
test('programmatic paging is not also driven by a controlled content offset', () => {
  const app = readFileSync(new URL('../../App.js', import.meta.url), 'utf8');
  assert.doesNotMatch(app, /contentOffset=\{\{ x: selectedGalleryIndex/);
  assert.match(app, /if \(!expandedGalleryNeedsPosition.current/);
});
