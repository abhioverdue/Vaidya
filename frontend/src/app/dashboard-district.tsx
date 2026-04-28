/**
 * Vaidya — District Health Dashboard  (Module 9)
 * Real-time district health overview with active outbreaks and KPIs
 */

import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
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

export default function DashboardDistrictScreen() {
  const { t } = useTranslation();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['dashboard-district'],
    queryFn: async () => ({
      district: 'Kancheepuram',
      period_hours: 24,
      total_sessions: 127,
      active_outbreaks: 3,
      triage_breakdown: { 1: 38, 2: 51, 3: 28, 4: 8, 5: 2 },
      top_diagnoses: [
        { diagnosis: 'Viral URI', count: 31 },
        { diagnosis: 'Gastroenteritis', count: 24 },
        { diagnosis: 'Hypertension', count: 19 },
        { diagnosis: 'Dengue (suspected)', count: 15 },
        { diagnosis: 'Anaemia', count: 12 },
      ],
      asha_performance: { active: 18, queue_size: 5 },
    }),
    staleTime: 300 * 1000,
  });

  const kpis = [
    {
      label: 'Sessions',
      value: data?.total_sessions ?? 0,
      color: COLORS.ink,
    },
    {
      label: 'Active ASHA',
      value: data?.asha_performance?.active ?? 0,
      color: COLORS.sage,
    },
    {
      label: 'Outbreaks',
      value: data?.active_outbreaks ?? 0,
      color: data?.active_outbreaks ? COLORS.crimson : COLORS.sage,
    },
  ];

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
          <SectionHeader
            title={`${data?.district ?? 'District'} Health Dashboard`}
            subtitle="Real-time overview"
          />
        </View>

        {/* KPI Cards */}
        <Animated.View entering={FadeInDown} style={styles.kpiRow}>
          {kpis.map((kpi, idx) => (
            <View key={idx} style={styles.kpiCard}>
              <Text style={styles.kpiValue}>{kpi.value}</Text>
              <Text style={[styles.kpiLabel, { color: kpi.color }]}>{kpi.label}</Text>
            </View>
          ))}
        </Animated.View>

        {/* Active Outbreaks */}
        {(data?.active_outbreaks ?? 0) > 0 && (
          <Animated.View entering={FadeInDown.delay(100)}>
            <TouchableOpacity
              style={[styles.alert, styles.alertRed]}
              onPress={() => router.push('/outbreaks')}
            >
              <Text style={styles.alertTitle}>⚠ {data?.active_outbreaks} Active Outbreak{(data?.active_outbreaks ?? 0) !== 1 ? 's' : ''}</Text>
              <Text style={styles.alertSub}>Tap to view details</Text>
            </TouchableOpacity>
          </Animated.View>
        )}

        {/* Top Diagnoses */}
        <Animated.View entering={FadeInDown.delay(150)}>
          <Text style={styles.sectionTitle}>Top Diagnoses (24h)</Text>
          <View style={styles.diagnosisList}>
            {(data?.top_diagnoses ?? []).slice(0, 5).map((d: any, idx: number) => (
              <View key={idx} style={styles.diagnosisRow}>
                <Text style={styles.diagnosisName}>{d.diagnosis}</Text>
                <Text style={styles.diagnosisCount}>{d.count}</Text>
              </View>
            ))}
          </View>
        </Animated.View>

        {/* Action Buttons */}
        <Animated.View entering={FadeInDown.delay(200)} style={styles.actionRow}>
          <TouchableOpacity style={styles.actionBtn} onPress={() => router.push('/hotspots')}>
            <Text style={styles.actionLabel}>📍 Hotspots</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => router.push('/trends')}>
            <Text style={styles.actionLabel}>📈 Trends</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => router.push('/predictions')}>
            <Text style={styles.actionLabel}>🔮 Forecast</Text>
          </TouchableOpacity>
        </Animated.View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { padding: 16, gap: 20, paddingBottom: 32 },
  header: { marginBottom: 8 },
  backBtn: { color: COLORS.ink, fontWeight: '600', fontSize: 14 },
  kpiRow: { flexDirection: 'row', gap: 10 },
  kpiCard: {
    flex: 1,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  kpiValue: { ...TYPE.headlineSmall, color: COLORS.ink },
  kpiLabel: { ...TYPE.micro, fontWeight: '700', marginTop: 4 },
  alert: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderLeftWidth: 4,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  alertRed: { borderLeftColor: COLORS.crimson },
  alertTitle: { ...TYPE.titleMed, color: COLORS.crimson, marginBottom: 4 },
  alertSub: { ...TYPE.micro, color: COLORS.textMuted },
  sectionTitle: { ...TYPE.titleMed, color: COLORS.ink, marginBottom: 8 },
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
  diagnosisName: { ...TYPE.bodySmall, color: COLORS.ink },
  diagnosisCount: { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '700' },
  actionRow: { flexDirection: 'row', gap: 8 },
  actionBtn: {
    flex: 1,
    backgroundColor: COLORS.ink,
    borderRadius: RADIUS.lg,
    paddingVertical: 12,
    alignItems: 'center',
  },
  actionLabel: { ...TYPE.bodySmall, color: '#fff', fontWeight: '600' },
});
