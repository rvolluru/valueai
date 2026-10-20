import test from 'node:test';
import assert from 'node:assert/strict';
import { matchPhotoUrls } from './matchPhotos.js';

test('match gallery opens the thumbnail first and deduplicates original URLs', () => {
  assert.deepEqual(matchPhotoUrls({ image: '/v1/images/hero', images: ['/v1/images/other', '/v1/images/hero'] }, 'http://localhost:8000'),
    ['http://localhost:8000/v1/images/hero', 'http://localhost:8000/v1/images/other']);
});
test('match gallery tolerates missing images and falls back to the first gallery photo', () => {
  assert.deepEqual(matchPhotoUrls({ images: [null, '/v1/images/one'] }, 'https://www.jouft.com'), ['https://www.jouft.com/v1/images/one']);
  assert.deepEqual(matchPhotoUrls({}, 'https://www.jouft.com'), []);
});
