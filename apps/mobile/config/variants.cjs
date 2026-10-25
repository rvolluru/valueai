const PRODUCTION_API = 'https://api.jouft.com';

function buildVariant(config, env = process.env) {
  const profile = env.APP_ENV || 'development';
  if (!['development', 'staging', 'production'].includes(profile)) throw Error('Unknown APP_ENV');
  if (env.EAS_BUILD_PROFILE && env.EAS_BUILD_PROFILE !== profile) throw Error('Build profile and APP_ENV must match');
  const production = profile === 'production';
  const api = profile === 'development' ? env.EXPO_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000'
    : production ? PRODUCTION_API : env.JOUFT_STAGING_API_URL;
  const key = profile === 'development' ? env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY || ''
    : production ? env.JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY : env.JOUFT_STAGING_CLERK_PUBLISHABLE_KEY;
  if (profile !== 'development') {
    if (!api) throw Error('Set JOUFT_STAGING_API_URL before building staging');
    const parsed = new URL(api);
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') {
      throw Error('Release API must be an HTTPS origin without credentials, path or query');
    }
    if (!production && ['api.jouft.com', 'jouft.com', 'www.jouft.com', 'localhost', '127.0.0.1', '::1', '[::1]'].includes(parsed.hostname)) {
      throw Error('Staging must not use production or localhost');
    }
    if (!key?.startsWith(production ? 'pk_live_' : 'pk_test_')) throw Error(`${profile} requires a ${production ? 'live' : 'test'} Clerk publishable key`);
    if (env.EXPO_PUBLIC_API_BASE_URL && env.EXPO_PUBLIC_API_BASE_URL.replace(/\/$/, '') !== api.replace(/\/$/, '')) {
      throw Error('EXPO_PUBLIC_API_BASE_URL conflicts with the selected release environment');
    }
    if (env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY && env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY !== key) throw Error('Conflicting Clerk configuration');
  }
  const identifier = production ? 'com.jouft.app' : 'com.jouft.app.dev';
  return {
    ...config, name: production ? 'JOUFT' : 'Jouft Testing', version: production ? '1.0.0' : '0.1.0', scheme: identifier,
    ios: { ...config.ios, bundleIdentifier: identifier }, android: { ...config.android, package: identifier },
    plugins: [...(config.plugins || []), ['expo-dev-client', { addGeneratedScheme: profile === 'development' }]],
    extra: { ...config.extra, appEnvironment: profile, appVariant: production ? 'production' : 'testing',
      apiBaseUrl: api.replace(/\/$/, ''), clerkPublishableKey: key || '' },
  };
}

module.exports = { buildVariant };
