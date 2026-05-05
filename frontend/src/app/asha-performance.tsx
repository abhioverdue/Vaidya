/**
 * Vaidya — ASHA Performance Analytics Dashboard
 * Supervisor view: district-level ASHA worker performance metrics
 * Calls GET /analytics/asha/performance?district_code=...&days_back=...
 * Demo fallback: 5 realistic ASHA workers with Tamil Nadu names
 */

import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useQuery } from '@tanstack/react-query';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { apiClient } from '@/services/api';
import { markDemoMode } from '@/services/demoData';

// ── Types ─────────────────────────────────────────────────────────────────────

interface AshaWorkerMetric {
  worker_id:           string;
  name:                string;
  village:             string;
  total_assignments:   number;
  acknowledgment_rate: number;   // 0–1
  completion_rate:     number;   // 0–1
  avg_response_time_h: number;   // hours
  referrals_count:     number;
}

interface PerformanceResponse {
  district_code:          string;
  period_days:            number;
  total_workers:          number;
  avg_acknowledgment_rate: number;
  workers:                AshaWorkerMetric[];
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_PERFORMANCE: PerformanceResponse = {
  district_code:          'TN-CBE',
  period_days:            30,
  total_workers:          5,
  avg_acknowledgment_rate: 0.74,
  workers: [
    {
      worker_id:           'asha-001',
      name:                'Meena Devi',
      village:             'Maduranthakam',
      total_assignments:   28,
      acknowledgment_rate: 0.93,
      completion_rate:     0.89,
      avg_response_time_h: 1.2,
      referrals_count:     4,
    },
    {
      worker_id:           'asha-002',
      name:                'Kavitha Selvi',
      village:             'Pollachi',
      total_assignments:   21,
      acknowledgment_rate: 0.81,
      completion_rate:     0.76,
      avg_response_time_h: 2.8,
      referrals_count:     3,
    },
    {
      worker_id:           'asha-003',
      name:                'Rani Murugesan',
      village:             'Mettupalayam',
      total_assignments:   34,
      acknowledgment_rate: 0.97,
      completion_rate:     0.94,
      avg_response_time_h: 0.9,
      referrals_count:     7,
    },
    {
      worker_id:           'asha-004',
      name:                'Lakshmi Pandiyan',
      village:             'Valparai',
      total_assignments:   15,
      acknowledgment_rate: 0.60,
      completion_rate:     0.53,
      avg_response_time_h: 5.4,
      referrals_count:     1,
    },
    {
      worker_id:           'asha-005',
      name:                'Selvi Arumugam',
      village:             'Annur',
      total_assignments:   19,
      acknowledgment_rate: 0.79,
      completion_rate:     0.68,
      avg_response_time_h: 3.1,
      referrals_count:     2,
    },
  ],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const DISTRICT_OPTIONS = [
  { code: 'TN-CBE', label: 'Coimbatore'  },
  { code: 'TN-MDS', label: 'Madurai'     },
  { code: 'TN-CHN', label: 'Chennai'     },
  { code: 'MH-PNE', label: 'Pune'        },
  { code: 'UP-LKW', label: 'Lucknow'     },
];

const PERIOD_OPTIONS: Array<{ days: number; label: string }> = [
  { days: 7,  label: '7 days'  },
  { days: 14, label: '14 days' },
  { days: 30, label: '30 days' },
];

const SORT_OPTIONS = [
  { key: 'completion_rate',    label: 'Completion rate' },
  { key: 'total_assignments',  label: 'Assignments'     },
] as const;

type SortKey = typeof SORT_OPTIONS[number]['key'];

function rateColor(rate: number): string {
  if (rate >= 0.8) return COLORS.sage;
  if (rate >= 0.6) return COLORS.gold;
  return COLORS.crimson;
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function RateBar({ rate, color }: { rate: number; color: string }) {
  return (
    <View style={pb.track}>
      <View style={[pb.fill, { width: `${Math.min(Math.round(rate * 100), 100)}%`, backgroundColor: color }]} />
    </View>
  );
}

const pb = StyleSheet.create({
  track: { flex: 1, height: 6, backgroundColor: COLORS.parchment, borderRadius: 3, overflow: 'hidden' },
  fill:  { height: '100%', borderRadius: 3 },
});

// ── Worker card ───────────────────────────────────────────────────────────────

function WorkerCard({ w, index }: { w: AshaWorkerMetric; index: number }) {
  const ackColor  = rateColor(w.acknowledgment_rate);
  const compColor = rateColor(w.completion_rate);

  return (
    <Animated.View entering={FadeInDown.duration(260).delay(index * 40)} style={wc.wrap}>
      <View style={wc.header}>
        <View style={wc.nameBlock}>
          <Text style={wc.name}>{w.name}</Text>
          <Text style={wc.village}>{w.village}</Text>
        </View>
        <View style={wc.statsRow}>
          <View style={wc.statPill}>
            <Text style={wc.statValue}>{w.total_assignments}</Text>
            <Text style={wc.statLabel}>assigned</Text>
          </View>
          <View style={wc.statPill}>
            <Text style={wc.statValue}>{w.referrals_count}</Text>
            <Text style={wc.statLabel}>referred</Text>
          </View>
        </View>
      </View>

      <View style={wc.metricsBlock}>
        {/* Acknowledgment rate */}
        <View style={wc.metricRow}>
          <Text style={wc.metricLabel}>Acknowledgment</Text>
          <View style={wc.metricRight}>
            <RateBar rate={w.acknowledgment_rate} color={ackColor} />
            <Text style={[wc.metricPct, { color: ackColor }]}>{pct(w.acknowledgment_rate)}</Text>
          </View>
        </View>

        {/* Completion rate */}
        <View style={wc.metricRow}>
          <Text style={wc.metricLabel}>Completion</Text>
          <View style={wc.metricRight}>
            <RateBar rate={w.completion_rate} color={compColor} />
            <Text style={[wc.metricPct, { color: compColor }]}>{pct(w.completion_rate)}</Text>
          </View>
        </View>

        {/* Avg response time */}
        <View style={wc.responseRow}>
          <Text style={wc.metricLabel}>Avg response</Text>
          <Text style={wc.responseVal}>{w.avg_response_time_h.toFixed(1)} h</Text>
        </View>
      </View>
    </Animated.View>
  );
}

const wc = StyleSheet.create({
  wrap:        {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 14, gap: 12,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
  },
  header:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  nameBlock:   { gap: 2, flex: 1 },
  name:        { ...TYPE.titleLarge, color: COLORS.ink },
  village:     { ...TYPE.micro, color: COLORS.textMuted },
  statsRow:    { flexDirection: 'row', gap: 8 },
  statPill:    {
    alignItems: 'center', paddingHorizontal: 10, paddingVertical: 5,
    backgroundColor: COLORS.parchment, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border,
  },
  statValue:   { fontSize: 14, fontWeight: '700', color: COLORS.ink },
  statLabel:   { ...TYPE.micro, color: COLORS.textMuted },
  metricsBlock:{ gap: 8 },
  metricRow:   { flexDirection: 'row', alignItems: 'center', gap: 10 },
  metricLabel: { width: 100, ...TYPE.bodyMed, color: COLORS.textMuted },
  metricRight: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  metricPct:   { fontSize: 12, fontWeight: '700', width: 36, textAlign: 'right' },
  responseRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  responseVal: { ...TYPE.bodyMed, color: COLORS.textSub, fontWeight: '600', marginLeft: 'auto' },
});

// ── API call ──────────────────────────────────────────────────────────────────

async function fetchPerformance(districtCode: string, daysBback: number): Promise<PerformanceResponse> {
  try {
    const { data } = await apiClient.get<PerformanceResponse>('/analytics/asha/performance', {
      params: { district_code: districtCode, days_back: daysBback },
    });
    return data;
  } catch {
    markDemoMode();
    await new Promise((r) => setTimeout(r, 800));
    return { ...DEMO_PERFORMANCE, district_code: districtCode, period_days: daysBback };
  }
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function AshaPerformanceScreen() {
  const [districtCode, setDistrictCode] = useState('TN-CBE');
  const [periodDays,   setPeriodDays]   = useState(30);
  const [sortKey,      setSortKey]      = useState<SortKey>('completion_rate');

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['asha-performance', districtCode, periodDays],
    queryFn:  () => fetchPerformance(districtCode, periodDays),
    staleTime: 2 * 60 * 1000,
    retry: 0,
  });

  const workers: AshaWorkerMetric[] = [...(data?.workers ?? [])].sort((a, b) => {
    if (sortKey === 'completion_rate')   return b.completion_rate - a.completion_rate;
    if (sortKey === 'total_assignments') return b.total_assignments - a.total_assignments;
    return 0;
  });

  const avgAck = data?.avg_acknowledgment_rate ?? 0;
  const totalWorkers = data?.total_workers ?? 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backArrow}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>ASHA Performance</Text>
        <View style={styles.headerSpacer} />
      </View>

      {/* District selector */}
      <ScrollView
        horizontal showsHorizontalScrollIndicator={false}
        style={styles.districtBar}
        contentContainerStyle={styles.districtBarContent}
      >
        {DISTRICT_OPTIONS.map((d) => {
          const active = districtCode === d.code;
          return (
            <TouchableOpacity
              key={d.code}
              style={[styles.districtChip, active && styles.districtChipActive]}
              onPress={() => setDistrictCode(d.code)}
              activeOpacity={0.75}
            >
              <Text style={[styles.districtChipText, active && styles.districtChipTextActive]}>
                {d.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
      >
        {/* Period filter */}
        <Animated.View entering={FadeInDown.duration(260)} style={styles.filterRow}>
          {PERIOD_OPTIONS.map((p) => {
            const active = periodDays === p.days;
            return (
              <TouchableOpacity
                key={p.days}
                style={[styles.periodChip, active && styles.periodChipActive]}
                onPress={() => setPeriodDays(p.days)}
                activeOpacity={0.75}
              >
                <Text style={[styles.periodChipText, active && styles.periodChipTextActive]}>{p.label}</Text>
              </TouchableOpacity>
            );
          })}
        </Animated.View>

        {/* Summary header */}
        {data && (
          <Animated.View entering={FadeInDown.duration(260).delay(40)} style={styles.summaryCard}>
            <View style={styles.summaryItem}>
              <Text style={styles.summaryValue}>{totalWorkers}</Text>
              <Text style={styles.summaryLabel}>Workers</Text>
            </View>
            <View style={styles.summaryDivider} />
            <View style={styles.summaryItem}>
              <Text style={[styles.summaryValue, { color: rateColor(avgAck) }]}>{pct(avgAck)}</Text>
              <Text style={styles.summaryLabel}>Avg ack. rate</Text>
            </View>
            <View style={styles.summaryDivider} />
            <View style={styles.summaryItem}>
              <Text style={styles.summaryValue}>{periodDays}d</Text>
              <Text style={styles.summaryLabel}>Period</Text>
            </View>
          </Animated.View>
        )}

        {/* Sort controls */}
        <Animated.View entering={FadeInDown.duration(260).delay(60)} style={styles.sortRow}>
          <Text style={styles.sortLabel}>Sort by:</Text>
          {SORT_OPTIONS.map((s) => {
            const active = sortKey === s.key;
            return (
              <TouchableOpacity
                key={s.key}
                style={[styles.sortBtn, active && styles.sortBtnActive]}
                onPress={() => setSortKey(s.key)}
                activeOpacity={0.75}
              >
                <Text style={[styles.sortBtnText, active && styles.sortBtnTextActive]}>{s.label}</Text>
              </TouchableOpacity>
            );
          })}
        </Animated.View>

        {/* Loading state */}
        {isLoading && !data && (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="large" color={COLORS.sage} />
            <Text style={styles.loadingText}>Loading performance data...</Text>
          </View>
        )}

        {/* Worker cards */}
        <View style={styles.workerList}>
          {workers.map((w, i) => (
            <WorkerCard key={w.worker_id} w={w} index={i} />
          ))}
        </View>

        {!isLoading && workers.length === 0 && (
          <View style={styles.emptyWrap}>
            <Text style={styles.emptyText}>No ASHA workers found for this district and period.</Text>
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.parchment },

  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 20, paddingVertical: 14,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
    gap: 12,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border,
  },
  backArrow:    { fontSize: 18, color: COLORS.ink, marginTop: -1 },
  headerTitle:  { ...TYPE.titleLarge, color: COLORS.ink, flex: 1 },
  headerSpacer: { width: 36 },

  districtBar:        { backgroundColor: COLORS.surface, borderBottomWidth: 1, borderBottomColor: COLORS.border, maxHeight: 52, flexShrink: 0 },
  districtBarContent: { paddingHorizontal: 16, paddingVertical: 10, gap: 6, flexDirection: 'row' },
  districtChip:       {
    paddingHorizontal: 14, paddingVertical: 6,
    backgroundColor: COLORS.parchment, borderRadius: RADIUS.pill,
    borderWidth: 1, borderColor: COLORS.border,
  },
  districtChipActive:    { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  districtChipText:      { fontSize: 12, fontWeight: '600', color: COLORS.textSub },
  districtChipTextActive:{ color: '#fff' },

  scroll: { padding: 16, gap: 14 },

  filterRow: { flexDirection: 'row', gap: 8 },
  periodChip: {
    flex: 1, paddingVertical: 10, alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border,
  },
  periodChipActive:    { backgroundColor: COLORS.sage, borderColor: COLORS.sage },
  periodChipText:      { fontSize: 12, fontWeight: '600', color: COLORS.textSub },
  periodChipTextActive:{ color: '#fff' },

  summaryCard: {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.border,
    flexDirection: 'row', padding: 16,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
  },
  summaryItem:    { flex: 1, alignItems: 'center', gap: 4 },
  summaryValue:   { fontSize: 22, fontWeight: '800', color: COLORS.ink, letterSpacing: -0.4 },
  summaryLabel:   { ...TYPE.micro, color: COLORS.textMuted },
  summaryDivider: { width: 1, backgroundColor: COLORS.border, marginVertical: 4 },

  sortRow:         { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sortLabel:       { ...TYPE.micro, color: COLORS.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 },
  sortBtn:         {
    paddingHorizontal: 12, paddingVertical: 6,
    backgroundColor: COLORS.surface, borderRadius: RADIUS.pill,
    borderWidth: 1, borderColor: COLORS.border,
  },
  sortBtnActive:   { backgroundColor: COLORS.parchmentWarm, borderColor: COLORS.borderMid },
  sortBtnText:     { fontSize: 11, fontWeight: '600', color: COLORS.textMuted },
  sortBtnTextActive:{ color: COLORS.ink },

  loadingWrap:  { alignItems: 'center', paddingVertical: 40, gap: 12 },
  loadingText:  { ...TYPE.bodyMed, color: COLORS.textMuted },

  workerList:   { gap: 12 },

  emptyWrap:   { alignItems: 'center', paddingVertical: 32 },
  emptyText:   { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center' },
});
