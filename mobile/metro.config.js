const { getDefaultConfig } = require('expo/metro-config');
const { transformer, resolver } = require('react-native-svg-transformer');

const config = getDefaultConfig(__dirname);

config.transformer = {
  ...config.transformer,
  ...transformer,
};

config.resolver = {
  ...resolver,
  ...config.resolver,
  assetExts: (config.resolver.assetExts || []).filter((ext) => ext !== 'svg'),
  sourceExts: [...(config.resolver.sourceExts || []), 'svg'],
};

module.exports = config;
