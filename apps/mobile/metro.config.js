const path = require('path');
const fs = require('fs');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
const monorepoPackagesRoot = path.resolve(__dirname, '../../packages');
const localPackagesRoot = path.resolve(__dirname, 'packages');
const packagesRoot = fs.existsSync(monorepoPackagesRoot)
  ? monorepoPackagesRoot
  : fs.existsSync(localPackagesRoot)
    ? localPackagesRoot
    : null;
const appClientRoot = packagesRoot ? path.join(packagesRoot, 'app-client') : null;

config.watchFolders = packagesRoot ? [packagesRoot] : [];

config.resolver.unstable_enableSymlinks = true;
config.resolver.extraNodeModules = appClientRoot && fs.existsSync(appClientRoot)
  ? {
      ...(config.resolver.extraNodeModules || {}),
      '@valueai/app-client': appClientRoot,
    }
  : config.resolver.extraNodeModules;

module.exports = config;
