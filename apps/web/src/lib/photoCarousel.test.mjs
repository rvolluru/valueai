import test from 'node:test';
import assert from 'node:assert/strict';
import { createPhotoCarousel, movePhotoCarousel } from './photoCarousel.mjs';
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
