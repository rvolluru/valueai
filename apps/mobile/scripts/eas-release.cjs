const { spawnSync } = require('node:child_process');
const [action, platform, profile, ...args] = process.argv.slice(2);
if (!['build', 'submit'].includes(action) || !['ios', 'android'].includes(platform) || !['staging', 'production'].includes(profile)) {
  throw Error('Usage: eas-release.cjs build|submit ios|android staging|production [EAS arguments]');
}
const command = action === 'submit' && profile === 'production'
  ? ['node', 'scripts/submit-production.cjs', platform, ...args]
  : ['eas', action, '--platform', platform, '--profile', profile, ...args];
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
const result = spawnSync('eas', ['env:exec', profile === 'staging' ? 'preview' : 'production',
  `APP_ENV=${profile} ${command.map(quote).join(' ')}`,
  ...(args.includes('--non-interactive') ? ['--non-interactive'] : [])], {
  stdio: 'inherit', env: { ...process.env, APP_ENV: 'development', EXPO_NO_DOTENV: '1' },
});
if (result.error) throw result.error;
process.exit(result.status || 0);
