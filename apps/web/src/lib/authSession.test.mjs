import test from 'node:test'
import assert from 'node:assert/strict'
import { isAlreadySignedInError } from './authSession.mjs'

test('recognizes an existing Clerk session without confusing credential failures', () => {
  assert.equal(isAlreadySignedInError({ errors: [{ code: 'session_exists' }] }), true)
  assert.equal(isAlreadySignedInError({ errors: [{ message: "You're already signed in." }] }), true)
  assert.equal(isAlreadySignedInError({ errors: [{ code: 'form_password_incorrect', message: 'Incorrect password.' }] }), false)
  assert.equal(isAlreadySignedInError(new Error('Network error')), false)
  assert.equal(isAlreadySignedInError(null), false)
})
