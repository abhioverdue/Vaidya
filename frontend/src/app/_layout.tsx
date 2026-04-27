/**
 * Vaidya — root layout
 * Initialises: i18n, TensorFlow, network monitoring, React Query, auth
 */

import '@/polyfills';

import { useEffect, useState, Component } from 'react';
import { View, ActivityIndicator, StyleSheet, Text, ScrollView } from 'react-native';

// ── Global crash handler — catches unhandled JS errors AND promise rejections
// that happen outside React's render tree (e.g. bootstrap async function).
// Must run before anything else.
let _showCrash: ((msg: string) => void) | null = null;

const origHandler = (global as any).ErrorUtils?.getGlobalHandler?.();
(global as any).ErrorUtils?.setGlobalHandler?.((error: Error, isFatal?: boolean) => {
  if (_showCrash) _showCrash(`[${isFatal ? 'FATAL' : 'ERROR'}] ${error?.message}\n\n${error?.stack}`);
  origHandler?.(error, isFatal);
});

// ── Error boundary — catches React render errors ──────────────────────────────
class ErrorBoundary extends Component<
  { children: React.ReactNode },
  { error: string | null }
> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error: `${error?.name}: ${error?.message}\n\n${error?.stack}` };
  }
  render() {
    if (this.state.error) return <CrashScreen message={this.state.error} />;
    return this.props.children;
  }
}

function CrashScreen({ message }: { message: string }) {
  return (
    <ScrollView style={{ flex: 1, backgroundColor: '#1a1a1a', padding: 24, paddingTop: 60 }}>
      <Text style={{ color: '#ff4444', fontSize: 16, fontWeight: 'bold', marginBottom: 12 }}>
        App crashed — screenshot and send to developer
      </Text>
      <Text style={{ color: '#fff', fontFamily: 'monospace', fontSize: 11, lineHeight: 17 }}>
        {message}
      </Text>
    </ScrollView>
  );
}

import { Stack, router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';

import { initI18n } from '@/i18n';
import i18n from '@/i18n';
import { loadOfflineModel } from '@/services/offlineModel';
import { useNetworkStatus } from '@/hooks/useNetworkStatus';
import { useAppStore } from '@/store';
import { COLORS } from '@/constants';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry:       2,
      staleTime:   5 * 60 * 1000,
      networkMode: 'always',
    },
  },
});

function AppInit({ children }: { children: React.ReactNode }) {
  useNetworkStatus();
  return <>{children}</>;
}

export default function RootLayout() {
  const [i18nReady, setI18nReady] = useState(false);
  const [crashMsg, setCrashMsg]   = useState<string | null>(null);
  const setReady    = useAppStore((s) => s.setReady);
  const loadHistory = useAppStore((s) => s.loadHistory);
  const loadPatient = useAppStore((s) => s.loadPatient);
  const loadAuth    = useAppStore((s) => s.loadAuth);

  // Wire up global crash handler to show on screen
  useEffect(() => {
    _showCrash = setCrashMsg;
    return () => { _showCrash = null; };
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        await initI18n();
        setI18nReady(true);
        await Promise.all([loadHistory(), loadPatient(), loadAuth()]);
        loadOfflineModel().catch(() => {});
        setReady(true);
      } catch (e: any) {
        setCrashMsg(`bootstrap error: ${e?.message}\n\n${e?.stack}`);
      }
    }
    bootstrap();
  }, []);

  if (crashMsg) return <CrashScreen message={crashMsg} />;

  if (!i18nReady) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <ErrorBoundary>
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <I18nextProvider i18n={i18n}>
          <QueryClientProvider client={queryClient}>
            <AppInit>
              <StatusBar style="dark" />
              <Stack screenOptions={{
                headerShown: false,
                animation: 'slide_from_right',
                contentStyle: { backgroundColor: COLORS.parchment },
              }}>
                <Stack.Screen name="login"          options={{ animation: 'fade' }} />
                <Stack.Screen name="register"       options={{ animation: 'slide_from_right' }} />
                <Stack.Screen name="verify-otp"     options={{ animation: 'slide_from_right' }} />
                <Stack.Screen name="reset-password" options={{ animation: 'slide_from_right' }} />
                <Stack.Screen name="language-select" options={{ animation: 'fade' }} />
                <Stack.Screen name="caution"  />
                <Stack.Screen name="consent"  />
                <Stack.Screen name="index"        options={{ animation: 'fade' }} />
                <Stack.Screen name="symptom"      />
                <Stack.Screen name="analysis"     />
                <Stack.Screen name="result"       />
                <Stack.Screen name="care"         />
                <Stack.Screen name="settings"     />
                <Stack.Screen name="audio-result" />
                <Stack.Screen name="image-result" />
                <Stack.Screen name="fusion-detail"/>
              </Stack>
            </AppInit>
          </QueryClientProvider>
        </I18nextProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  root:   { flex: 1, backgroundColor: COLORS.parchment },
  splash: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.parchment },
});
