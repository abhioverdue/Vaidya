/**
 * Vaidya — Find Nearby ASHA Workers  (Module 6)
 * Search for nearest ASHA workers using GPS location
 */

import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, Linking, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import * as Location from 'expo-location';
import { useState, useEffect } from 'react';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { OfflineBanner } from '@/components/ui/OfflineBanner';

export default function AshaNearbyScreen() {
  const { t } = useTranslation();
  const [location, setLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [loadingLoc, setLoadingLoc] = useState(true);

  useEffect(() => {
    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') {
        const loc = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        setLocation({
          lat: loc.coords.latitude,
          lng: loc.coords.longitude,
        });
      }
      setLoadingLoc(false);
    })();
  }, []);

  const DEMO_WORKERS = [
    { id: 'asha-001', name: 'Meena Devi', village: 'Maduranthakam', phone: '9876543210', distance_km: 1.2 },
    { id: 'asha-002', name: 'Lakshmi Bai', village: 'Kancheepuram West', phone: '9845123456', distance_km: 2.8 },
    { id: 'asha-003', name: 'Saraswathi R.', village: 'Padalam Block', phone: '9712345678', distance_km: 4.5 },
    { id: 'asha-004', name: 'Kamala Selvam', village: 'Singaperumalkoil', phone: '9634567890', distance_km: 6.1 },
    { id: 'asha-005', name: 'Valli Krishnan', village: 'Uthiramerur', phone: '9512398765', distance_km: 9.3 },
  ];

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['asha-nearby', location?.lat, location?.lng],
    queryFn: async () => ({
      query: { lat: location?.lat, lng: location?.lng, radius_km: 25 },
      count: DEMO_WORKERS.length,
      workers: DEMO_WORKERS,
    }),
    enabled: !!location,
    staleTime: 120 * 1000,
  });

  const workers = data?.workers ?? [];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <OfflineBanner />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backBtn}>← Back</Text>
        </TouchableOpacity>
        <SectionHeader title="Nearby ASHA Workers" subtitle={`${workers.length} found`} />
      </View>

      {loadingLoc && (
        <View style={styles.centerSpinner}>
          <ActivityIndicator size="large" color={COLORS.ink} />
          <Text style={styles.spinnerText}>Getting your location...</Text>
        </View>
      )}

      {!loadingLoc && !location && (
        <View style={styles.centerSpinner}>
          <Text style={styles.errorText}>Location access denied</Text>
          <Text style={styles.spinnerText}>Enable location in settings to find nearby workers</Text>
        </View>
      )}

      {location && (
        <FlatList
          data={workers}
          keyExtractor={(w) => w.id}
          refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
          renderItem={({ item, index }) => (
            <Animated.View entering={FadeInDown.delay(index * 50)}>
              <TouchableOpacity style={styles.card} activeOpacity={0.7}>
                <View style={styles.body}>
                  <View style={styles.nameRow}>
                    <Text style={styles.name}>{item.name}</Text>
                    <View style={styles.distBadge}>
                      <Text style={styles.distText}>{item.distance_km.toFixed(1)} km</Text>
                    </View>
                  </View>
                  {item.village && <Text style={styles.village}>{item.village}</Text>}
                  <Text style={styles.phone}>{item.phone}</Text>
                </View>
                <TouchableOpacity
                  style={styles.callBtn}
                  onPress={() => Linking.openURL(`tel:${item.phone}`)}
                >
                  <Text style={styles.callText}>Call</Text>
                </TouchableOpacity>
              </TouchableOpacity>
            </Animated.View>
          )}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.emptyText}>
                {isLoading ? 'Searching for nearby workers...' : 'No ASHA workers found nearby'}
              </Text>
            </View>
          }
          contentContainerStyle={{ padding: 16, gap: 8 }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.parchment },
  header: { paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  backBtn: { color: COLORS.ink, fontWeight: '600', fontSize: 14 },
  centerSpinner: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 8 },
  spinnerText: { ...TYPE.bodySmall, color: COLORS.textMuted },
  errorText: { ...TYPE.titleMed, color: COLORS.crimson },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  body: { flex: 1, gap: 4 },
  nameRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { ...TYPE.titleMed, color: COLORS.ink, flex: 1 },
  distBadge: { backgroundColor: COLORS.sageGhost, borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 4 },
  distText: { ...TYPE.micro, color: COLORS.sage, fontWeight: '700' },
  village: { ...TYPE.micro, color: COLORS.textMuted },
  phone: { ...TYPE.bodySmall, color: COLORS.ink, fontWeight: '600' },
  callBtn: { backgroundColor: COLORS.sage, borderRadius: RADIUS.md, paddingHorizontal: 16, paddingVertical: 10 },
  callText: { ...TYPE.bodySmall, color: '#fff', fontWeight: '700' },
  empty: { alignItems: 'center', paddingVertical: 48 },
  emptyText: { ...TYPE.bodyMed, color: COLORS.textMuted },
});
