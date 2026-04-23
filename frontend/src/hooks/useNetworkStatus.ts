/**
 * Vaidya — network status hook
 * Subscribes to NetInfo, updates Zustand store, shows offline banner.
 */

import { useEffect, useRef } from 'react';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import { useAppStore } from '@/store';

export function useNetworkStatus() {
  const setOnline = useAppStore((s) => s.setOnline);
  const isOnline  = useAppStore((s) => s.isOnline);

  useEffect(() => {
    // Get initial state
    // Note: isInternetReachable is null on Android until checked — treat null as online
    // so the app doesn't incorrectly fall into offline mode on first load.
    NetInfo.fetch().then((state: NetInfoState) => {
      setOnline(Boolean(state.isConnected && state.isInternetReachable !== false));
    });

    // Subscribe to changes
    const unsubscribe = NetInfo.addEventListener((state: NetInfoState) => {
      setOnline(Boolean(state.isConnected && state.isInternetReachable !== false));
    });

    return () => unsubscribe();
  }, [setOnline]);

  return { isOnline };
}
