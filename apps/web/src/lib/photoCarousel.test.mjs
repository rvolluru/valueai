import test from 'node:test';
import assert from 'node:assert/strict';
import { createPhotoCarousel, movePhotoCarousel } from './photoCarousel.mjs';
import { isMannequinImage } from '../../../../packages/app-client/src/mannequinDisclosure.js';
test('disclosure follows the current carousel photo in either direction', () => {
  const listing = { generatedImages: ['ai'] };
  let state = createPhotoCarousel({ src: 'original', images: ['original', 'ai'], disclosureListing: listing });
  assert.equal(isMannequinImage(state.disclosureListing, state.src), false);
  state = movePhotoCarousel(state, 1);
  assert.equal(isMannequinImage(state.disclosureListing, state.src), true);
  state = movePhotoCarousel(state, -1);
  assert.equal(isMannequinImage(state.disclosureListing, state.src), false);
});
test('opens the selected photo and cycles both directions', () => {
  const state = createPhotoCarousel({ src: 'b', images: ['a', 'b', 'c'] });
  assert.equal(state.index, 1);
  assert.equal(movePhotoCarousel(state, 1).src, 'c');
  assert.equal(movePhotoCarousel(movePhotoCarousel(state, 1), 1).src, 'a');
  assert.equal(movePhotoCarousel(movePhotoCarousel(state, -1), -1).src, 'c');
});
test('single image remains unchanged', () => {
  const state = createPhotoCarousel({ src: 'a' });
  assert.equal(movePhotoCarousel(state, 1), state);
});
