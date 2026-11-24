import test from 'node:test'
import assert from 'node:assert/strict'
import { reviewDescription } from './reviewDescription.mjs'
test('removes repeated summary facts and retains item details', () => {
  assert.equal(reviewDescription('Brand: Chanel\nClassic loafers. Size: 38\nCondition: Like New\nPrice: $250.00\nQuilted leather. Quilted leather. Minor scuff on the left heel.', { brand: 'Chanel', title: 'Classic loafers', size: '38', condition: 'Like New', price: '$250.00' }), 'Quilted leather.\n\nMinor scuff on the left heel.')
})
test('retains condition and size statements with additional evidence', () => {
  assert.equal(reviewDescription('Condition: Like New with a small mark. Size: 38, fits narrow.', { condition: 'Like New', size: '38' }), 'Condition: Like New with a small mark.\n\nSize: 38, fits narrow.')
})
test('removes generated title and matching generic condition', () => {
  assert.equal(reviewDescription("Chanel Loafers. It's in like-new condition. It features gold hardware.", { brand: 'Chanel', model: 'Loafers', condition: 'Like New' }), 'It features gold hardware.')
})
