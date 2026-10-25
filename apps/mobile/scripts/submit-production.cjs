const { spawnSync } = require('node:child_process');
const eas = require('../eas.json');
const platform = process.argv[2] || 'ios';
if (!['ios', 'android'].includes(platform)) throw Error('Choose ios or android');
const id = eas.submit.production.ios.ascAppId;
if (platform === 'ios' && (!/^\d+$/.test(id || '') || id === eas.submit.staging.ios.ascAppId)) {
  throw Error('Create the com.jouft.app App Store Connect record and set its NEW ascAppId in submit.production.ios. Do not reuse the testing record.');
}
const result = spawnSync('eas', ['submit', '--platform', platform, '--profile', 'production', ...process.argv.slice(3)], {
  stdio: 'inherit', env: { ...process.env, APP_ENV: 'production', EXPO_NO_DOTENV: '1' },
});
if (result.error) throw result.error;
process.exit(result.status || 0);
