/**
 * Vaidya — Disease Hotspots  (Module 9)
 * Geospatial visualization of disease hotspots
 */

import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { OfflineBanner } from '@/components/ui/OfflineBanner';

export default function HotspotsScreen() {
  const { t } = useTranslation();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['hotspots'],
    queryFn: async () => ({
      hotspots: [
        { location: 'Kancheepuram Town', primary_diseases: ['Dengue', 'Malaria'], case_density: 4.2 },
        { location: 'Chengalpattu Block', primary_diseases: ['Gastroenteritis', 'Typhoid'], case_density: 3.1 },
        { location: 'Maduranthakam', primary_diseases: ['Dengue', 'Influenza A'], case_density: 2.8 },
        { location: 'Tambaram East', primary_diseases: ['Respiratory Illness', 'Influenza'], case_density: 2.3 },
        { location: 'Sriperumbudur', primary_diseases: ['Anaemia', 'Malnutrition'], case_density: 1.9 },
      ],
      generated_at: new Date().toISOString(),
    }),
    staleTime: 300 * 1000,
  });

  const hotspots = data?.hotspots ?? [];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <OfflineBanner />

      <ScrollView
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
        contentContainerStyle={styles.scroll}
      >
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()}>
            <Text style={styles.backBtn}>← Back</Text>
          </TouchableOpacity>
          <SectionHeader title="Disease Hotspots" subtitle="Geographic clusters" />
        </View>

        {hotspots.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No hotspots detected</Text>
            <Text style={styles.emptySubText}>Disease distribution is normal across regions</Text>
          </View>
        ) : (
          <Animated.View entering={FadeInDown} style={styles.hotspotsGrid}>
            {hotspots.map((h: any, idx: number) => (
              <View key={idx} style={styles.hotspotCard}>
                <View style={[styles.hotspotDot, { backgroundColor: `hsl(${idx * 60}, 70%, 50%)` }]} />
                <Text style={styles.hotspotName}>{h.location}</Text>
                <Text style={styles.hotspotDiseases}>{h.primary_diseases?.join(', ')}</Text>
                <Text style={styles.hotspotCount}>{h.case_density}/km²</Text>
              </View>
            ))}
          </Animated.View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { padding: 16, gap: 20, paddingBottom: 32 },
  header: { marginBottom: 8 },
  backBtn: { color: COLORS.ink, fontWeight: '600', fontSize: 14 },
  empty: { alignItems: 'center', paddingVertical: 48 },
  emptyText: { ...TYPE.titleMed, color: COLORS.sage },
  emptySubText: { ...TYPE.micro, color: COLORS.textMuted, marginTop: 4 },
  hotspotsGrid: { gap: 12 },
  hotspotCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 6,
  },
  hotspotDot: { width: 20, height: 20, borderRadius: 10 },
  hotspotName: { ...TYPE.titleMed, color: COLORS.ink },
  hotspotDiseases: { ...TYPE.micro, color: COLORS.textMuted },
  hotspotCount: { ...TYPE.bodySmall, color: COLORS.ink, fontWeight: '700' },
});
