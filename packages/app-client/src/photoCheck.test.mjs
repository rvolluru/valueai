import test from 'node:test';
import assert from 'node:assert/strict';
import { PHOTO_CHECK_TIMEOUT_MS, withPhotoCheckTimeout } from './photoCheck.js';
test('initial photo check uses thirty seconds', () => assert.equal(PHOTO_CHECK_TIMEOUT_MS, 30000));
test('successful check returns normally', async () => assert.equal(await withPhotoCheckTimeout(async () => 'ok', 100), 'ok'));
test('deadline aborts and ignores a late result', async () => {
  let signal;
  await assert.rejects(withPhotoCheckTimeout(s => { signal = s; return new Promise(resolve => setTimeout(() => resolve('late'), 30)); }, 5), error => error.code === 'photo_check_timeout');
  assert.equal(signal.aborted, true);
});
