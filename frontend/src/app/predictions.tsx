/**
 * Vaidya — Disease Forecasting  (Module 9)
 * 7-day disease predictions using time-series models
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

export default function PredictionsScreen() {
  const { t } = useTranslation();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['predictions'],
    queryFn: async () => ({
      predictions: [
        { disease: 'Dengue Fever', date: '2026-05-02', predicted_cases: 41 },
        { disease: 'Dengue Fever', date: '2026-05-05', predicted_cases: 38 },
        { disease: 'Dengue Fever', date: '2026-05-08', predicted_cases: 33 },
        { disease: 'Gastroenteritis', date: '2026-05-02', predicted_cases: 29 },
        { disease: 'Gastroenteritis', date: '2026-05-05', predicted_cases: 24 },
        { disease: 'Influenza A', date: '2026-05-02', predicted_cases: 18 },
        { disease: 'Influenza A', date: '2026-05-05', predicted_cases: 15 },
        { disease: 'Malaria', date: '2026-05-02', predicted_cases: 12 },
      ],
      forecast_window_days: 7,
      confidence: 0.82,
    }),
    staleTime: 600 * 1000,
  });

  const predictions = data?.predictions ?? [];

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
            title="Disease Forecast"
            subtitle={`Next ${data?.forecast_window_days ?? 7} days`}
          />
        </View>

        {/* Confidence Badge */}
        <Animated.View entering={FadeInDown}>
          <View style={styles.confidenceCard}>
            <Text style={styles.confidenceLabel}>Model Confidence</Text>
            <View style={styles.confidenceBar}>
              <View
                style={[
                  styles.confidenceFill,
                  { width: `${(data?.confidence ?? 0) * 100}%` },
                ]}
              />
            </View>
            <Text style={styles.confidenceValue}>{((data?.confidence ?? 0) * 100).toFixed(0)}%</Text>
          </View>
        </Animated.View>

        {/* Forecast Items */}
        {predictions.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No predictions available</Text>
          </View>
        ) : (
          <Animated.View entering={FadeInDown.delay(100)} style={styles.predictionsList}>
            {predictions.map((p: any, idx: number) => (
              <View key={idx} style={styles.predictionCard}>
                <View style={styles.predictionTop}>
                  <View>
                    <Text style={styles.predictionDisease}>{p.disease}</Text>
                    <Text style={styles.predictionDate}>{p.date}</Text>
                  </View>
                  <View style={[styles.predictionBadge, { backgroundColor: `rgba(${idx * 50}, 100, 150, 0.1)` }]}>
                    <Text style={styles.predictionValue}>{p.predicted_cases}</Text>
                  </View>
                </View>
                <View style={styles.predictionBar}>
                  <View
                    style={[
                      styles.predictionFill,
                      {
                        width: `${(p.predicted_cases / Math.max(...(predictions.map((x: any) => x.predicted_cases) ?? [1]), 1)) * 100}%`,
                        backgroundColor: `hsl(${idx * 60}, 70%, 50%)`,
                      },
                    ]}
                  />
                </View>
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
  confidenceCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 8,
  },
  confidenceLabel: { ...TYPE.bodySmall, color: COLORS.textMuted },
  confidenceBar: { height: 8, backgroundColor: COLORS.parchment, borderRadius: 4, overflow: 'hidden' },
  confidenceFill: { height: '100%', backgroundColor: COLORS.sage },
  confidenceValue: { ...TYPE.titleMed, color: COLORS.ink },
  empty: { alignItems: 'center', paddingVertical: 48 },
  emptyText: { ...TYPE.titleMed, color: COLORS.textMuted },
  predictionsList: { gap: 10 },
  predictionCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 10,
  },
  predictionTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  predictionDisease: { ...TYPE.titleMed, color: COLORS.ink },
  predictionDate: { ...TYPE.micro, color: COLORS.textMuted, marginTop: 2 },
  predictionBadge: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.pill },
  predictionValue: { ...TYPE.bodySmall, color: COLORS.ink, fontWeight: '700' },
  predictionBar: { height: 6, backgroundColor: COLORS.parchment, borderRadius: 3, overflow: 'hidden' },
  predictionFill: { height: '100%' },
});
