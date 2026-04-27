// metro.config.js
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const config = getDefaultConfig(__dirname);

const STUB = path.resolve(__dirname, 'src/stubs/nativeStub.js');

const defaultSourceExts = config.resolver?.sourceExts ?? [];
const defaultAssetExts  = config.resolver?.assetExts  ?? [];

// DO NOT prepend web.ts/web.tsx to sourceExts.
// Metro's platform-specific resolution already handles .web.ts for web builds
// (it tries <module>.web.<ext> before <module>.<ext> when building for web).
// Putting web.ts first in sourceExts caused Metro to pick nativeModule.web.ts
// from @react-native-community/netinfo on Android instead of nativeModule.ts,
// crashing the app with "TypeError: undefined is not a function" in addListener.

// Register ML model formats as binary assets so require() returns an asset
// reference (used by expo-asset). Without this Metro tries to parse them as
// JS source files and throws "Unable to resolve module".
//
// Mutate config.resolver directly instead of spreading it.  In Expo SDK 51
// the resolver object may have getter-defined properties; spreading loses
// those and silently reverts assetExts to Metro's internal defaults, so
// .onnx / .tflite files end up parsed as JS source and their binary content
// leaks into the module value (causing the "missing from asset registry" error).
const modelAssetExts = ['onnx', 'tflite', 'bin', 'pb'];
config.resolver.assetExts = [
  ...defaultAssetExts.filter((e) => !modelAssetExts.includes(e)),
  ...modelAssetExts,
];
config.resolver.sourceExts = defaultSourceExts;

config.resolver.resolveRequest = (context, moduleName, platform) => {
    // Fix @expo/metro-runtime bug: Library → Libraries
    if (moduleName.startsWith('react-native/Library/')) {
      const fixed = moduleName.replace('react-native/Library/', 'react-native/Libraries/');
      return context.resolveRequest(context, fixed, platform);
    }

    // On native, stub crypto only when imported from expo-modules-core uuid
    if (
      moduleName === 'crypto' &&
      (platform === 'android' || platform === 'ios') &&
      context.originModulePath &&
      context.originModulePath.includes('expo-modules-core')
    ) {
      return { filePath: STUB, type: 'sourceFile' };
    }

    if (platform === 'web') {
      const nodePolyfills = {
        crypto: require.resolve('crypto-browserify'),
        stream: require.resolve('stream-browserify'),
        buffer: path.resolve(__dirname, 'node_modules/buffer/index.js'),
      };
      if (nodePolyfills[moduleName]) {
        return { filePath: nodePolyfills[moduleName], type: 'sourceFile' };
      }

      const nativeOnlyModules = [
        'react-native-maps',
        'onnxruntime-react-native',
      ];
      if (nativeOnlyModules.some((m) => moduleName === m || moduleName.startsWith(m + '/'))) {
        return { filePath: STUB, type: 'sourceFile' };
      }
    }

    return context.resolveRequest(context, moduleName, platform);
  };

module.exports = config;
