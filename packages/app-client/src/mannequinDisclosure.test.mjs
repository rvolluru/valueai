import test from 'node:test';
import assert from 'node:assert/strict';
import { isMannequinImage } from './mannequinDisclosure.js';

const listing = { analysis: { generated_assets: [
  { synthetic: true, kind: 'mannequin_bottom', image_url: '/v1/images/ai', review_decision: 'pending' },
  { synthetic: true, kind: 'white_background', image_url: '/v1/images/staged' },
  { synthetic: true, kind: 'mannequin_bottom', image_url: '/v1/images/excluded', review_decision: 'exclude' },
] } };
test('disclaimer applies only to the selected mannequin image', () => {
  assert.equal(isMannequinImage(listing, '/v1/images/original'), false);
  assert.equal(isMannequinImage(listing, 'https://api.jouft.com/v1/images/ai?x=1'), true);
  assert.equal(isMannequinImage(listing, '/v1/images/staged'), false);
  assert.equal(isMannequinImage(listing, '/v1/images/excluded'), false);
  assert.equal(isMannequinImage(listing, null), false);
});
test('supports generated and marked gallery metadata', () => {
  assert.equal(isMannequinImage({ generatedImages: ['/v1/images/ai'] }, '/v1/images/ai'), true);
  assert.equal(isMannequinImage({ listedImages: [{ d_img: '/v1/images/ai', role_hint: 'ai_mannequin' }] }, '/v1/images/ai'), true);
});

test('closet cards prefer mannequin previews and retain original fallback', async () => {
  const { closetCardImages } = await import('./mannequinDisclosure.js');
  const originals = ['/v1/images/original', '/v1/images/back'];
  assert.deepEqual(closetCardImages(listing, originals), ['/v1/images/ai', ...originals]);
  assert.deepEqual(closetCardImages({}, originals), originals);
  assert.deepEqual(closetCardImages({ analysis: { generated_assets: [listing.analysis.generated_assets[2]] } }, originals), originals);
  assert.deepEqual(closetCardImages({ listedImages: [{ d_img: '/v1/images/marked', role_hint: 'ai_mannequin' }] }, originals), ['/v1/images/marked', ...originals]);
});
