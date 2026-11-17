const { spawnSync } = require('node:child_process');
const [action, platform, profile, ...args] = process.argv.slice(2);
if (!['build', 'submit'].includes(action) || !['ios', 'android'].includes(platform) || !['staging', 'production', 'production-simulator'].includes(profile)) {
  throw Error('Usage: eas-release.cjs build|submit ios|android staging|production|production-simulator [EAS arguments]');
}
if (profile === 'production-simulator' && (action !== 'build' || platform !== 'ios')) {
  throw Error('production-simulator only supports iOS builds; it cannot be submitted.');
}
const appEnvironment = profile === 'production-simulator' ? 'production' : profile;
const command = action === 'submit' && profile === 'production'
  ? ['node', 'scripts/submit-production.cjs', platform, ...args]
  : ['eas', action, '--platform', platform, '--profile', profile, ...args];
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
const result = spawnSync('eas', ['env:exec', profile === 'staging' ? 'preview' : 'production',
  `APP_ENV=${appEnvironment} ${command.map(quote).join(' ')}`,
  ...(args.includes('--non-interactive') ? ['--non-interactive'] : [])], {
  stdio: 'inherit', env: { ...process.env, APP_ENV: 'development', EXPO_NO_DOTENV: '1' },
});
if (result.error) throw result.error;
process.exit(result.status || 0);
