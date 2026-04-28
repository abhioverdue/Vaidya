/**
 * Vaidya — Outbreak Management  (Module 9)
 * List and manage active disease outbreak alerts
 */

import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { OfflineBanner } from '@/components/ui/OfflineBanner';

export default function OutbreaksScreen() {
  const { t } = useTranslation();

  const DEMO_OUTBREAKS = [
    { id: 'ob-001', disease: 'Dengue Fever', location: 'Kancheepuram District', district: 'Kancheepuram', case_count: 34, severity: 'high' },
    { id: 'ob-002', disease: 'Gastroenteritis Cluster', location: 'Chengalpattu Block', district: 'Chengalpattu', case_count: 12, severity: 'medium' },
    { id: 'ob-003', disease: 'Influenza A (H1N1)', location: 'Maduranthakam Taluk', district: 'Kancheepuram', case_count: 8, severity: 'low' },
  ];

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['outbreaks-active'],
    queryFn: async () => ({
      total: DEMO_OUTBREAKS.length,
      outbreaks: DEMO_OUTBREAKS,
    }),
    staleTime: 120 * 1000,
  });

  const outbreaks = data?.outbreaks ?? [];

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'high':
        return COLORS.crimson;
      case 'medium':
        return '#F5A623';
      case 'low':
        return COLORS.sage;
      default:
        return COLORS.textMuted;
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <OfflineBanner />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backBtn}>← Back</Text>
        </TouchableOpacity>
        <SectionHeader title="Active Outbreaks" subtitle={`${outbreaks.length} alert${outbreaks.length !== 1 ? 's' : ''}`} />
      </View>

      <FlatList
        data={outbreaks}
        keyExtractor={(o) => o.id}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeInDown.delay(index * 50)}>
            <TouchableOpacity
              style={styles.card}
              activeOpacity={0.7}
              onPress={() => router.push(`/outbreak-detail?id=${item.id}`)}
            >
              <View style={[styles.severityDot, { backgroundColor: getSeverityColor(item.severity) }]} />
              <View style={styles.body}>
                <Text style={styles.disease}>{item.disease}</Text>
                <Text style={styles.location}>{item.location}</Text>
                <View style={styles.meta}>
                  <Text style={styles.metaText}>{item.case_count} cases</Text>
                  <Text style={styles.metaDot}>•</Text>
                  <Text style={styles.metaText}>{item.district}</Text>
                </View>
              </View>
              <Text style={styles.arrow}>→</Text>
            </TouchableOpacity>
          </Animated.View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>
              {isLoading ? 'Loading outbreaks...' : 'No active outbreaks'}
            </Text>
            <Text style={styles.emptySubText}>All clear! No disease alerts detected.</Text>
          </View>
        }
        contentContainerStyle={{ padding: 16, gap: 8 }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.parchment },
  header: { paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  backBtn: { color: COLORS.ink, fontWeight: '600', fontSize: 14 },
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
  severityDot: { width: 10, height: 10, borderRadius: 5 },
  body: { flex: 1, gap: 4 },
  disease: { ...TYPE.titleMed, color: COLORS.ink },
  location: { ...TYPE.micro, color: COLORS.textMuted },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metaText: { ...TYPE.micro, color: COLORS.textSub },
  metaDot: { color: COLORS.textFaint },
  arrow: { fontSize: 14, color: COLORS.textFaint },
  empty: { alignItems: 'center', paddingVertical: 48 },
  emptyText: { ...TYPE.titleMed, color: COLORS.sage },
  emptySubText: { ...TYPE.micro, color: COLORS.textMuted, marginTop: 4 },
});
