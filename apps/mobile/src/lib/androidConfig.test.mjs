import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const config = JSON.parse(readFileSync(new URL('../../app.json', import.meta.url), 'utf8')).expo;
const eas = JSON.parse(readFileSync(new URL('../../eas.json', import.meta.url), 'utf8'));

test('Android preview has an app identifier and installable APK profile', () => {
  assert.equal(config.android.package, 'com.jouft.app');
  assert.equal(config.name, 'JOUFT');
  assert.equal(eas.build.preview.android.buildType, 'apk');
});
test('camera does not enable microphone or location permissions', () => {
  assert.ok(config.android.permissions.includes('android.permission.CAMERA'));
  assert.ok(config.android.blockedPermissions.includes('android.permission.RECORD_AUDIO'));
  assert.ok(config.android.blockedPermissions.includes('android.permission.ACCESS_FINE_LOCATION'));
  assert.ok(!config.plugins.some(plugin => (Array.isArray(plugin) ? plugin[0] : plugin) === 'expo-location'));
});
