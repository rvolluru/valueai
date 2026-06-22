const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
const appClientRoot = path.resolve(__dirname, '../../packages/app-client');

config.watchFolders = [
  path.resolve(__dirname, '../../packages'),
];

config.resolver.unstable_enableSymlinks = true;
config.resolver.extraNodeModules = {
  ...(config.resolver.extraNodeModules || {}),
  '@valueai/app-client': appClientRoot,
};

module.exports = config;
