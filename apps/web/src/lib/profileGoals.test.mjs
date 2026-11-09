import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeProfileGoals, needsGoalSelection, JOUFT_GOAL_OPTIONS } from './profileGoals.js'

test('legacy hidden goals require reselection and release both choice slots', () => {
  const legacy = ['Sustainable Fashion', 'Discover Rare Finds']
  assert.equal(needsGoalSelection(legacy), true)
  const choices = normalizeProfileGoals(legacy)
  assert.deepEqual(choices, [])
  choices.push(JOUFT_GOAL_OPTIONS[0], JOUFT_GOAL_OPTIONS[1])
  assert.equal(needsGoalSelection(choices), false)
  assert.deepEqual(normalizeProfileGoals(choices), choices)
})
test('current choices remain selected and empty or excessive goals require setup', () => {
  assert.deepEqual(normalizeProfileGoals(['Trade Instead of Sell']), ['Trade Instead of Sell'])
  for (const goals of [null, [], JOUFT_GOAL_OPTIONS]) assert.equal(needsGoalSelection(goals), true)
})
