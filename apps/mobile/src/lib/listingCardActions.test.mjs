import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.js', import.meta.url), 'utf8');
const card = app.slice(app.indexOf('function ListingCard('), app.indexOf('function OfferCard('));

test('closet cards have no parent touch handler over their action buttons', () => {
  assert.match(card, /const CardContainer = onOpenDetails && !closet \? TouchableOpacity : View/);
  assert.match(card, /const cardContainerProps = onOpenDetails && !closet/);
});

test('review overlay is confined to the photo area before the card body', () => {
  const photoStart = card.indexOf('<View style={styles.listingPhotoArea}>');
  const review = card.indexOf('accessibilityLabel="Review and publish listing"');
  const photoEnd = card.indexOf('{closet && Number.isFinite(matchCount)');
  const bodyStart = card.indexOf('styles.listingBody');
  assert.ok(photoStart >= 0 && photoStart < review && review < photoEnd && photoEnd < bodyStart);
  assert.equal(card.match(/accessibilityLabel="Review and publish listing"/g).length, 1);
});

test('More uses an anchored dismissible dropdown, not a native options alert', () => {
  assert.doesNotMatch(card, /Alert\.alert\('More options'/);
  assert.match(card, /measureInWindow/);
  assert.match(card, /accessibilityLabel="Close listing options"/);
  assert.match(card, /onRequestClose=\{\(\) => setMoreMenuAnchor\(null\)\}/);
});
