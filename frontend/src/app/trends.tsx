import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { useTranslation } from 'react-i18next';
import { COLORS, TYPE, RADIUS } from '@/constants';
import { OfflineBanner } from '@/components/ui/OfflineBanner';
import { apiClient } from '@/services/api';

const DISEASE_OPTIONS = [
  'Dengue Fever',
  'Gastroenteritis',
  'Influenza A',
  'Malaria',
  'Hypertension',
];

const DEMO_TRENDS: Record<string, { disease: string; change: number; points: number[] }> = {
  'Dengue Fever':    { disease: 'Dengue Fever',             change: 18.4, points: [12, 14, 16, 19, 22, 28, 34] },
  'Gastroenteritis': { disease: 'Gastroenteritis',          change: 5.2,  points: [18, 20, 22, 19, 21, 24, 26] },
  'Influenza A':     { disease: 'Influenza A',              change: -8.1, points: [24, 22, 20, 18, 17, 16, 15] },
  'Malaria':         { disease: 'Malaria (P. falciparum)',  change: 54.7, points: [5, 6, 7, 9, 12, 18, 31] },
  'Hypertension':    { disease: 'Hypertension',             change: -1.5, points: [35, 34, 36, 33, 34, 32, 31] },
};

export default function TrendsScreen() {
  const { t } = useTranslation();
  const [selectedDisease, setSelectedDisease] = useState(DISEASE_OPTIONS[0]);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['trends', selectedDisease],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get('/analytics/trends', {
          params: { district_code: 'TN-CBE', diagnosis: selectedDisease, days_back: 30 },
        });
        const points = (data.data_points ?? []).map((p: any) => p.case_count ?? 0);
        const growthRate = data.growth_rate ?? 0;
        return {
          trends: [{
            disease: data.diagnosis ?? selectedDisease,
            change: growthRate,
            points: points.length > 0 ? points : DEMO_TRENDS[selectedDisease]?.points ?? [],
          }],
          period_days: data.days_back ?? 30,
        };
      } catch {
        const demo = DEMO_TRENDS[selectedDisease] ?? DEMO_TRENDS['Dengue Fever'];
        return { trends: [demo], period_days: 30 };
      }
    },
    staleTime: 300 * 1000,
  });

  const trends = data?.trends ?? [];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      <OfflineBanner />

      <View style={styles.nav}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.backBtn}>← Back</Text>
        </TouchableOpacity>
        <View style={styles.navTitle}>
          <Text style={styles.title}>{t('analytics.trends_title')}</Text>
          <Text style={styles.subtitle}>{t('analytics.last_days', { count: data?.period_days ?? 30 })}</Text>
        </View>
      </View>

      {/* Disease selector */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.pickerRow}
      >
        {DISEASE_OPTIONS.map((disease) => (
          <TouchableOpacity
            key={disease}
            style={[styles.pickerChip, selectedDisease === disease && styles.pickerChipActive]}
            onPress={() => setSelectedDisease(disease)}
            activeOpacity={0.7}
          >
            <Text style={[styles.pickerText, selectedDisease === disease && styles.pickerTextActive]}>
              {disease}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <ScrollView
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} tintColor={COLORS.textMuted} />}
        contentContainerStyle={styles.scroll}
      >
        {trends.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No trend data</Text>
          </View>
        ) : (
          <Animated.View entering={FadeInDown} style={styles.trendsList}>
            {trends.map((trend: any, idx: number) => {
              const rising = (trend.change ?? 0) > 0;
              const col = rising ? COLORS.crimson : COLORS.sage;
              const points: number[] = trend.points ?? [];
              const maxPt = Math.max(...points, 1);
              const CHART_HEIGHT = 56;

              return (
                <View key={idx} style={styles.trendCard}>
                  <View style={styles.trendHeader}>
                    <Text style={styles.diseaseName}>{trend.disease}</Text>
                    <View style={[styles.changeBadge, { backgroundColor: col + '18' }]}>
                      <Text style={[styles.changeText, { color: col }]}>
                        {rising ? '+' : ''}{(trend.change ?? 0).toFixed(1)}%
                      </Text>
                    </View>
                  </View>

                  {/* Sparkline */}
                  <View style={[styles.sparkline, { height: CHART_HEIGHT }]}>
                    {points.map((p, pi) => {
                      const h = 4 + (p / maxPt) * (CHART_HEIGHT - 4);
                      return (
                        <View
                          key={pi}
                          style={[
                            styles.bar,
                            {
                              height: h,
                              backgroundColor: pi === points.length - 1
                                ? col
                                : col + '55',
                            },
                          ]}
                        />
                      );
                    })}
                  </View>

                  <View style={styles.trendFooter}>
                    <Text style={styles.trendFooterLeft}>
                      {points.length > 0 ? t('analytics.cases_now', { count: points[points.length - 1] }) : ''}
                    </Text>
                    <Text style={styles.trendFooterRight}>{t('analytics.rolling_avg')}</Text>
                  </View>
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

  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  backBtn: { ...TYPE.bodySmall, color: COLORS.textSub, fontWeight: '600' },
  navTitle: { flex: 1 },
  title: { ...TYPE.titleLarge, color: COLORS.ink },
  subtitle: { ...TYPE.micro, color: COLORS.textMuted, marginTop: 2 },

  pickerRow: {
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  pickerChip: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: RADIUS.pill,
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  pickerChipActive: { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  pickerText: { ...TYPE.micro, color: COLORS.textSub, fontWeight: '600' },
  pickerTextActive: { color: '#fff' },

  scroll: { padding: 16, paddingBottom: 40 },
  trendsList: { gap: 10 },

  trendCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
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
  changeBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.pill },
  changeText: { ...TYPE.micro, fontWeight: '700' },

  sparkline: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 3,
  },
  bar: { flex: 1, borderRadius: 2, minHeight: 4 },

  trendFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  trendFooterLeft: { ...TYPE.micro, color: COLORS.textSub, fontWeight: '600' },
  trendFooterRight: { ...TYPE.micro, color: COLORS.textMuted },

  empty: { alignItems: 'center', paddingVertical: 56 },
  emptyText: { ...TYPE.bodySmall, color: COLORS.textMuted },
});
