/**
 * Vaidya — Outbreak Details  (Module 9)
 * Detailed view of a specific outbreak alert
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
import { OfflineBanner } from '@/components/ui/OfflineBanner';

export default function OutbreakDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();

  const DEMO_DETAILS: Record<string, any> = {
    'ob-001': {
      id: 'ob-001', disease: 'Dengue Fever', location: 'Kancheepuram', district: 'Kancheepuram',
      severity: 'high', case_count: 34, fatality_count: 1, affected_area: '3 panchayats',
      onset_date: '2026-04-18',
      description: 'Cluster of dengue cases across 3 panchayats following heavy rainfall. Aedes aegypti breeding sites confirmed.',
      recommendations: [
        'Eliminate standing water around homes and fields',
        'Use mosquito nets and repellent daily',
        'Seek care immediately for fever >101°F with rash',
        'Report new cases to nearest ASHA worker',
      ],
      public_health_measures: ['Vector control fogging', 'Door-to-door screening'],
      contact_person: 'Dr. Rajeswari S.', contact_phone: '044-27261204', acknowledged: false,
    },
    'ob-002': {
      id: 'ob-002', disease: 'Gastroenteritis Cluster', location: 'Chengalpattu', district: 'Chengalpattu',
      severity: 'medium', case_count: 12, fatality_count: 0, affected_area: '1 block',
      onset_date: '2026-04-22',
      description: 'Multiple gastroenteritis cases linked to contaminated water source in Chengalpattu block.',
      recommendations: [
        'Boil all drinking water for at least 5 minutes',
        'Wash hands with soap before meals and after toilet use',
        'Use ORS immediately for diarrhoea and vomiting',
        'Report water-source issues to panchayat office',
      ],
      public_health_measures: ['Water chlorination', 'Sample testing'],
      contact_person: 'Dr. Murugan P.', contact_phone: '044-27452301', acknowledged: false,
    },
    'ob-003': {
      id: 'ob-003', disease: 'Influenza A (H1N1)', location: 'Maduranthakam', district: 'Kancheepuram',
      severity: 'low', case_count: 8, fatality_count: 0, affected_area: '2 villages',
      onset_date: '2026-04-24',
      description: 'Seasonal H1N1 influenza cases detected in Maduranthakam taluk. All cases mild to moderate.',
      recommendations: [
        'Cover mouth and nose when coughing or sneezing',
        'Avoid crowded places if symptomatic',
        'Seek oseltamivir treatment within 48 hours of symptoms',
        'Isolate at home for 5 days after symptoms begin',
      ],
      public_health_measures: ['School health screening', 'Antiviral distribution'],
      contact_person: 'Dr. Anitha K.', contact_phone: '044-27445512', acknowledged: true,
    },
  };

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['outbreak', id],
    queryFn: async () =>
      DEMO_DETAILS[id ?? ''] ?? {
        id, disease: 'Unknown Outbreak', location: 'Region', district: 'District',
        severity: 'medium', case_count: 0, fatality_count: 0, affected_area: '-',
        onset_date: '-', description: 'Details unavailable.', recommendations: [],
        public_health_measures: [], contact_person: '-', contact_phone: '-', acknowledged: false,
      },
    enabled: !!id,
    staleTime: 120 * 1000,
  });

  const outbreak = data;
  const canAcknowledge = !data?.acknowledged;

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

        {/* Main Alert Card */}
        <Animated.View entering={FadeInDown}>
          <View style={styles.alertCard}>
            <View style={styles.alertHeader}>
              <Text style={styles.disease}>{outbreak?.disease}</Text>
              <View style={[styles.severityBadge, { backgroundColor: getSeverityBg(outbreak?.severity) }]}>
                <Text style={[styles.severityText, { color: getSeverityColor(outbreak?.severity) }]}>
                  {(outbreak?.severity ?? 'unknown').toUpperCase()}
                </Text>
              </View>
            </View>
            <Text style={styles.location}>{outbreak?.location}, {outbreak?.district}</Text>
          </View>
        </Animated.View>

        {/* Stats */}
        <Animated.View entering={FadeInDown.delay(100)} style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{outbreak?.case_count ?? 0}</Text>
            <Text style={styles.statLabel}>Cases</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statValue}>{outbreak?.fatality_count ?? 0}</Text>
            <Text style={styles.statLabel}>Deaths</Text>
          </View>
        </Animated.View>

        {/* Details */}
        <Animated.View entering={FadeInDown.delay(150)}>
          <Text style={styles.sectionTitle}>Details</Text>
          <View style={styles.detailCard}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Onset Date:</Text>
              <Text style={styles.detailValue}>{outbreak?.onset_date}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Affected Area:</Text>
              <Text style={styles.detailValue}>{outbreak?.affected_area}</Text>
            </View>
            {outbreak?.description && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Description:</Text>
                <Text style={styles.detailValue}>{outbreak.description}</Text>
              </View>
            )}
          </View>
        </Animated.View>

        {/* Recommendations */}
        {(outbreak?.recommendations?.length ?? 0) > 0 && (
          <Animated.View entering={FadeInDown.delay(200)}>
            <Text style={styles.sectionTitle}>Recommendations</Text>
            {outbreak?.recommendations?.map((r: string, idx: number) => (
              <View key={idx} style={styles.recommendationRow}>
                <Text style={styles.bullet}>•</Text>
                <Text style={styles.recommendationText}>{r}</Text>
              </View>
            ))}
          </Animated.View>
        )}

        {/* Action Buttons */}
        <Animated.View entering={FadeInDown.delay(250)} style={styles.actionRow}>
          {canAcknowledge && (
            <TouchableOpacity
              style={styles.acknowledgeBtn}
              onPress={() => {
                // TODO: POST /api/v1/analytics/outbreaks/{id}/acknowledge
              }}
            >
              <Text style={styles.acknowledgeBtnText}>Acknowledge Alert</Text>
            </TouchableOpacity>
          )}
        </Animated.View>
      </ScrollView>
    </SafeAreaView>
  );
}

function getSeverityColor(severity: string | undefined) {
  switch (severity?.toLowerCase()) {
    case 'high':
      return COLORS.crimson;
    case 'medium':
      return '#F5A623';
    case 'low':
      return COLORS.sage;
    default:
      return COLORS.textMuted;
  }
}

function getSeverityBg(severity: string | undefined) {
  const color = getSeverityColor(severity);
  switch (severity?.toLowerCase()) {
    case 'high':
      return 'rgba(194, 59, 34, 0.1)';
    case 'medium':
      return 'rgba(245, 166, 35, 0.1)';
    case 'low':
      return 'rgba(58, 95, 82, 0.1)';
    default:
      return 'rgba(0, 0, 0, 0.05)';
  }
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { padding: 16, gap: 20, paddingBottom: 32 },
  header: { marginBottom: 8 },
  backBtn: { color: COLORS.ink, fontWeight: '600', fontSize: 14 },
  alertCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 8,
  },
  alertHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  disease: { ...TYPE.headlineMed, color: COLORS.ink, flex: 1 },
  severityBadge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.pill },
  severityText: { ...TYPE.micro, fontWeight: '700' },
  location: { ...TYPE.bodySmall, color: COLORS.textMuted },
  statsRow: {
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
  detailCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 12,
  },
  detailRow: { gap: 4 },
  detailLabel: { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '600' },
  detailValue: { ...TYPE.bodySmall, color: COLORS.ink },
  recommendationRow: {
    flexDirection: 'row',
    gap: 8,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: 6,
  },
  bullet: { color: COLORS.textMuted, fontWeight: '700' },
  recommendationText: { ...TYPE.bodySmall, color: COLORS.ink, flex: 1 },
  actionRow: { gap: 8, paddingTop: 8 },
  acknowledgeBtn: {
    backgroundColor: COLORS.ink,
    borderRadius: RADIUS.lg,
    paddingVertical: 14,
    alignItems: 'center',
  },
  acknowledgeBtnText: { ...TYPE.titleMed, color: '#fff' },
});
