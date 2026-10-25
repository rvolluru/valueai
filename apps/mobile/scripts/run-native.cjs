const { spawnSync } = require('node:child_process');
const platform = process.argv[2];
if (!['ios', 'android'].includes(platform)) throw Error('Choose ios or android');
const env = { ...process.env, APP_ENV: 'development' };
for (const args of [['expo', 'prebuild', '--platform', platform, '--no-install'], ['expo', `run:${platform}`, ...process.argv.slice(3)]]) {
  const result = spawnSync('npx', args, { env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
