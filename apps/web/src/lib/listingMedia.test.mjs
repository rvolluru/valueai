import assert from 'node:assert/strict';
import { test } from 'node:test';
import { reconcileListingImages } from './listingMedia.mjs';

const previous = [
  { p_img: 'front-original', d_img: 'front-processed', is_hero: true },
  { p_img: 'label-original', d_img: 'label-processed', is_hero: false },
];
test('adding a third photo does not retain a stale two-photo payload', () => {
  assert.deepEqual(reconcileListingImages(['front-processed', 'label-processed', 'new-back'], previous), [
    ...previous, { p_img: 'new-back', d_img: 'new-back', is_hero: false },
  ]);
});
test('removing and replacing photos preserves only the current selection', () => {
  assert.deepEqual(reconcileListingImages(['front-processed', 'replacement'], previous), [
    previous[0], { p_img: 'replacement', d_img: 'replacement', is_hero: false },
  ]);
});
test('changing the hero preserves source mapping and sets exactly one hero', () => {
  assert.deepEqual(reconcileListingImages(['label-processed', 'front-processed'], previous), [
    { ...previous[1], is_hero: true }, { ...previous[0], is_hero: false },
  ]);
});
