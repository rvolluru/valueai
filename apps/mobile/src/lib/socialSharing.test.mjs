import test from 'node:test';
import assert from 'node:assert/strict';
import { shareSocialListing, socialWebUrl } from './socialSharing.mjs';
const payload = { shareUrl: 'https://jouft.com/item?a=1&b=2', imageUrl: 'https://jouft.com/photo.jpg', caption: 'My bag', title: 'Bag' };

for (const target of ['facebook', 'pinterest']) {
  test(`Android ${target} opens installed native share target`, async () => {
    let called;
    await shareSocialListing({ target, payload, platform: 'android', nativeShare: {
      Social: { FACEBOOK: 'facebook', PINTEREST: 'pinterest' },
      isPackageInstalled: async name => { assert.equal(name, target === 'facebook' ? 'com.facebook.katana' : 'com.pinterest'); return { isInstalled: true }; },
      shareSingle: async options => { called = options; },
    }, browserFallback: () => assert.fail('Must not open browser'), systemShare: () => assert.fail('Must use app') });
    assert.equal(called.social, target);
    assert.equal(called.url, payload.shareUrl);
  });
  test(`iOS ${target} uses native system sharing without forcing browser`, async () => {
    let called;
    await shareSocialListing({ target, payload, platform: 'ios', systemShare: async options => { called = options; }, browserFallback: () => assert.fail() });
    assert.equal(called.url, payload.shareUrl);
  });
}
test('missing app offers browser fallback and cancelled native sharing does not', async () => {
  let fallback = 0;
  const options = { target: 'facebook', payload, platform: 'android', browserFallback: () => fallback++,
    nativeShare: { isPackageInstalled: async () => ({ isInstalled: false }) } };
  await shareSocialListing(options);
  assert.equal(fallback, 1);
  await shareSocialListing({ ...options, nativeShare: { Social: { FACEBOOK: 'facebook' }, isPackageInstalled: async () => ({ isInstalled: true }), shareSingle: async () => { throw Error('User did not share'); } } });
  assert.equal(fallback, 1);
});
test('browser sharing encodes listing and image URLs', () => {
  const url = new URL(socialWebUrl('pinterest', payload));
  assert.equal(url.searchParams.get('url'), payload.shareUrl);
  assert.equal(url.searchParams.get('media'), payload.imageUrl);
});
