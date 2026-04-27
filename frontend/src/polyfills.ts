import { Platform } from 'react-native';
import { Buffer } from 'buffer';
import process from 'process';

// BUILD MARKER — if this appears in logcat the bundle is fresh
console.log('[VAIDYA] BUILD-2026-04-26-E-firebase-lazy');

// ── Global error handler — runs before React mounts ───────────────────────────
// Catches fatal JS errors that happen before the error boundary is mounted.
// Shows the error as an alert so it's visible even if the UI never renders.
const _orig = (global as any).ErrorUtils?.getGlobalHandler?.();
(global as any).ErrorUtils?.setGlobalHandler?.((error: Error, isFatal?: boolean) => {
  if (isFatal) {
    // Use setTimeout so the alert shows after RN initialises the UI thread
    setTimeout(() => {
      const { Alert } = require('react-native');
      Alert.alert(
        'Fatal crash — screenshot & send to dev',
        `${error?.name}: ${error?.message}\n\n${String(error?.stack).slice(0, 600)}`,
      );
    }, 500);
  }
  _orig?.(error, isFatal);
});

// react-native-get-random-values patches crypto.getRandomValues on native.
if (Platform.OS !== 'web') {
  require('react-native-get-random-values');
}

global.Buffer = Buffer;
global.process = process;
