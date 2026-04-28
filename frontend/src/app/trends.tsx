/**
 * Vaidya — Disease Trends  (Module 9)
 * Time-series disease trends over time
 */

import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, FlatList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { OfflineBanner } from '@/components/ui/OfflineBanner';

export default function TrendsScreen() {
  const { t } = useTranslation();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['trends'],
    queryFn: async () => ({
      trends: [
        { disease: 'Dengue Fever', change: 18.4, points: [12, 14, 16, 19, 22, 28, 34] },
        { disease: 'Gastroenteritis', change: 5.2, points: [18, 20, 22, 19, 21, 24, 26] },
        { disease: 'Influenza A', change: -8.1, points: [24, 22, 20, 18, 17, 16, 15] },
        { disease: 'Malaria', change: 2.3, points: [8, 9, 8, 10, 11, 10, 12] },
        { disease: 'Hypertension', change: -1.5, points: [35, 34, 36, 33, 34, 32, 31] },
      ],
      period_days: 30,
    }),
    staleTime: 300 * 1000,
  });

  const trends = data?.trends ?? [];

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
          <SectionHeader title="Disease Trends" subtitle={`Last ${data?.period_days ?? 30} days`} />
        </View>

        {trends.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No trend data</Text>
          </View>
        ) : (
          <Animated.View entering={FadeInDown} style={styles.trendsList}>
            {trends.map((t: any, idx: number) => {
              const isIncreasing = (t.change ?? 0) > 0;
              return (
                <View key={idx} style={styles.trendCard}>
                  <View style={styles.trendHeader}>
                    <Text style={styles.diseaseName}>{t.disease}</Text>
                    <View style={[styles.changeBadge, { backgroundColor: isIncreasing ? 'rgba(194,59,34,0.1)' : 'rgba(58,95,82,0.1)' }]}>
                      <Text style={[styles.changeText, { color: isIncreasing ? COLORS.crimson : COLORS.sage }]}>
                        {isIncreasing ? '↑' : '↓'} {Math.abs(t.change ?? 0).toFixed(1)}%
                      </Text>
                    </View>
                  </View>
                  <View style={styles.sparkline}>
                    {(t.points ?? []).map((p: number, pi: number) => {
                      const h = 2 + (p / Math.max(...(t.points ?? [1]), 1)) * 28;
                      return (
                        <View
                          key={pi}
                          style={[styles.bar, { height: h, backgroundColor: isIncreasing ? COLORS.crimson : COLORS.sage }]}
                        />
                      );
                    })}
                  </View>
                  <Text style={styles.trendFooter}>7-day rolling avg</Text>
                </View>
              );
            })}
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
  emptyText: { ...TYPE.titleMed, color: COLORS.textMuted },
  trendsList: { gap: 12 },
  trendCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 10,
  },
  trendHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  diseaseName: { ...TYPE.titleMed, color: COLORS.ink },
  changeBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.pill },
  changeText: { ...TYPE.micro, fontWeight: '700' },
  sparkline: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 2,
    height: 32,
  },
  bar: { flex: 1, borderRadius: 2 },
  trendFooter: { ...TYPE.micro, color: COLORS.textMuted, textAlign: 'right' },
});
