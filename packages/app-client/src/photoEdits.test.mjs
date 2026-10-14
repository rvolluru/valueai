import test from 'node:test';
import assert from 'node:assert/strict';
import { cropPixels } from './photoEdits.js';

test('full photo preserves dimensions', () => {
  assert.deepEqual(cropPixels(1200, 1600, { x: 0, y: 0, width: 100, height: 100 }),
    { originX: 0, originY: 0, width: 1200, height: 1600 });
});
test('crop percentages map to source pixels, independent of preview zoom', () => {
  assert.deepEqual(cropPixels(1200, 1600, { x: 10, y: 25, width: 80, height: 50 }),
    { originX: 120, originY: 400, width: 960, height: 800 });
});
test('crop clamps to image edges and retains at least one pixel', () => {
  const result = cropPixels(3, 5, { x: 99, y: 99, width: 200, height: 200 });
  assert.deepEqual(result, { originX: 2, originY: 4, width: 1, height: 1 });
});
test('rotated dimensions map crop correctly', () => {
  assert.deepEqual(cropPixels(1600, 1200, { x: 0, y: 0, width: 50, height: 100 }),
    { originX: 0, originY: 0, width: 800, height: 1200 });
});
