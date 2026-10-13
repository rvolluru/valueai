import assert from 'node:assert/strict';
import { test } from 'node:test';
import { appendListingPhotos, remainingPhotoSlots } from './listingPhotos.mjs';

const photo = (id) => ({ uri: `file://photo-${id}.jpg` });

test('one camera session adds multiple photos in capture order', () => {
  assert.deepEqual(appendListingPhotos([], [photo(1), photo(2), photo(3)]), [photo(1), photo(2), photo(3)]);
});
test('additional sessions preserve existing photos and hero order', () => {
  assert.deepEqual(appendListingPhotos([photo(1)], [photo(2), photo(3)]), [photo(1), photo(2), photo(3)]);
});
test('camera and library additions cannot exceed six total photos', () => {
  assert.equal(appendListingPhotos([photo(1)], Array.from({ length: 8 }, (_, i) => photo(i + 2))).length, 6);
});
test('editing counts saved listing photos as well as new photos', () => {
  assert.deepEqual(appendListingPhotos([photo(1)], [photo(2), photo(3), photo(4)], 4), [photo(1), photo(2)]);
  assert.equal(remainingPhotoSlots(5), 1);
  assert.equal(remainingPhotoSlots(6), 0);
  assert.equal(remainingPhotoSlots(7), 0);
});
test('cancelled sessions and invalid captures leave existing photos unchanged', () => {
  assert.deepEqual(appendListingPhotos([photo(1)], []), [photo(1)]);
  assert.deepEqual(appendListingPhotos([photo(1)], [null, {}, photo(2)]), [photo(1), photo(2)]);
});
