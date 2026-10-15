import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const app = readFileSync(new URL('../../App.js', import.meta.url), 'utf8');

test('review photos open the complete gallery at the tapped photo', () => {
  assert.match(app, /onPress=\{\(\) => openExpandedGallery\(gallery, idx\)\}/);
  assert.match(app, /setSelectedGalleryImages\(gallery\)/);
  assert.match(app, /setSelectedGalleryIndex\(safeIndex\)/);
});
test('full-screen carousel pages use measured width without flex compression', () => {
  assert.match(app, /horizontal\s+pagingEnabled/);
  assert.match(app, /width: expandedGalleryWidth/);
  const slide = app.slice(app.indexOf('galleryModalSlide: {'), app.indexOf('galleryModalImage: {'));
  assert.match(slide, /flexShrink: 0/);
  assert.doesNotMatch(slide, /flex: 1/);
  assert.match(app, /accessibilityLabel="Previous photo"/);
  assert.match(app, /accessibilityLabel="Next photo"/);
});
