/**
 * Vaidya — ASHA Worker Stats  (Module 6)
 * Activity statistics for an individual ASHA worker
 */

import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { OfflineBanner } from '@/components/ui/OfflineBanner';

export default function AshaStatsScreen() {
  const { t } = useTranslation();
  const { worker_id } = useLocalSearchParams<{ worker_id: string }>();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['asha-stats', worker_id],
    queryFn: async () => ({
      worker_id: worker_id ?? 'asha-001',
      worker_name: 'Meena Devi',
      village: 'Maduranthakam',
      period_days: 30,
      total_sessions: 47,
      by_triage_level: { '1': 12, '2': 18, '3': 11, '4': 5, '5': 1 },
      top_diagnoses: [
        { diagnosis: 'Viral URI', count: 9 },
        { diagnosis: 'Gastroenteritis', count: 7 },
        { diagnosis: 'Hypertension', count: 6 },
        { diagnosis: 'Malaria (suspected)', count: 5 },
        { diagnosis: 'Anaemia', count: 4 },
      ],
    }),
    enabled: true,
    staleTime: 120 * 1000,
  });

  const stats = data;
  const triageBreakdown = Object.entries(stats?.by_triage_level ?? {})
    .map(([level, count]) => ({
      level: parseInt(level),
      count: count as number,
      label: ['Self-care', 'Monitor', 'Visit PHC', 'Urgent', 'Emergency'][parseInt(level) - 1],
    }))
    .sort((a, b) => a.level - b.level);

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
        </View>

        {/* Worker Card */}
        <Animated.View entering={FadeInDown}>
          <View style={styles.workerCard}>
            <Text style={styles.workerName}>{stats?.worker_name}</Text>
            <Text style={styles.workerSub}>{stats?.village}</Text>
          </View>
        </Animated.View>

        {/* Summary Stats */}
        <Animated.View entering={FadeInDown.delay(100)} style={styles.summaryRow}>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{stats?.total_sessions ?? 0}</Text>
            <Text style={styles.statLabel}>Sessions</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{stats?.period_days ?? 30}</Text>
            <Text style={styles.statLabel}>Days</Text>
          </View>
        </Animated.View>

        {/* Triage Breakdown */}
        <Animated.View entering={FadeInDown.delay(150)}>
          <Text style={styles.sectionTitle}>Sessions by Urgency</Text>
          <View style={styles.breakdownList}>
            {triageBreakdown.map((item, idx) => (
              <View key={item.level} style={styles.breakdownRow}>
                <Text style={styles.breakdownLabel}>{item.label}</Text>
                <View style={styles.breakdownBar}>
                  <View
                    style={[
                      styles.breakdownFill,
                      {
                        width: `${(item.count / Math.max(...triageBreakdown.map(t => t.count), 1)) * 100}%`,
                        backgroundColor: ['#5C9B6D', '#4A90E2', '#F5A623', '#D0021B', '#C2371B'][item.level - 1],
                      },
                    ]}
                  />
                </View>
                <Text style={styles.breakdownCount}>{item.count}</Text>
              </View>
            ))}
          </View>
        </Animated.View>

        {/* Top Diagnoses */}
        {(stats?.top_diagnoses?.length ?? 0) > 0 && (
          <Animated.View entering={FadeInDown.delay(200)}>
            <Text style={styles.sectionTitle}>Most Common Diagnoses</Text>
            <View style={styles.diagnosisList}>
              {stats?.top_diagnoses?.map((d: any, idx: number) => (
                <View key={idx} style={styles.diagnosisRow}>
                  <Text style={styles.diagnosisName}>{d.diagnosis}</Text>
                  <Text style={styles.diagnosisCount}>{d.count}x</Text>
                </View>
              ))}
            </View>
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
  workerCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl,
    padding: 20,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 4,
  },
  workerName: { ...TYPE.headlineMed, color: COLORS.ink },
  workerSub: { ...TYPE.bodySmall, color: COLORS.textMuted },
  summaryRow: {
    flexDirection: 'row',
    gap: 12,
  },
  stat: {
    flex: 1,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  statValue: { ...TYPE.headlineSmall, color: COLORS.ink },
  statLabel: { ...TYPE.micro, color: COLORS.textMuted, marginTop: 4 },
  sectionTitle: { ...TYPE.titleMed, color: COLORS.ink, marginBottom: 8 },
  breakdownList: { gap: 8 },
  breakdownRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    padding: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  breakdownLabel: { ...TYPE.bodySmall, color: COLORS.textSub, width: 70 },
  breakdownBar: { flex: 1, height: 8, backgroundColor: COLORS.parchment, borderRadius: 4, overflow: 'hidden' },
  breakdownFill: { height: '100%' },
  breakdownCount: { ...TYPE.micro, color: COLORS.textMuted, fontWeight: '700', width: 30, textAlign: 'right' },
  diagnosisList: { gap: 6 },
  diagnosisRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  diagnosisName: { ...TYPE.bodySmall, color: COLORS.ink, flex: 1 },
  diagnosisCount: { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '700' },
});
