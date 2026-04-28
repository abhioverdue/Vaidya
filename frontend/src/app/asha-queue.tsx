/**
 * Vaidya — ASHA Worker Queue  (Module 6)
 * Patient queue for an ASHA worker — ordered by triage level (most urgent first)
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

const TRIAGE_COLORS = {
  1: COLORS.sage,
  2: '#4A90E2',
  3: '#F5A623',
  4: '#D0021B',
  5: '#C2371B',
};

const TRIAGE_LABELS = {
  1: 'Self-care',
  2: 'Monitor',
  3: 'Visit PHC',
  4: 'Urgent',
  5: 'Emergency',
};

export default function AshaQueueScreen() {
  const { t } = useTranslation();

  const DEMO_QUEUE = [
    { session_id: 'q-001', primary_diagnosis: 'Dengue Fever (suspected)', triage_level: 4, red_flags: ['High fever >104°F', 'Rash on arms'], language: 'Tamil', duration: '15 min' },
    { session_id: 'q-002', primary_diagnosis: 'Acute Gastroenteritis', triage_level: 3, red_flags: ['Dehydration risk'], language: 'Tamil', duration: '12 min' },
    { session_id: 'q-003', primary_diagnosis: 'Type 2 Diabetes (uncontrolled)', triage_level: 3, red_flags: ['High blood glucose >300'], language: 'Tamil', duration: '11 min' },
    { session_id: 'q-004', primary_diagnosis: 'Viral Upper Respiratory Infection', triage_level: 2, red_flags: [], language: 'Tamil', duration: '8 min' },
    { session_id: 'q-005', primary_diagnosis: 'Hypertension (stage 2)', triage_level: 3, red_flags: ['BP 160/100'], language: 'English', duration: '10 min' },
    { session_id: 'q-006', primary_diagnosis: 'Tension Headache', triage_level: 1, red_flags: [], language: 'Tamil', duration: '6 min' },
  ];

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['asha-queue'],
    queryFn: async () => ({
      count: DEMO_QUEUE.length,
      queue: DEMO_QUEUE,
    }),
    staleTime: 60 * 1000,
  });

  const sessions = data?.queue ?? [];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <OfflineBanner />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backBtn}>← Back</Text>
        </TouchableOpacity>
        <SectionHeader title="Patient Queue" subtitle={`${sessions.length} waiting`} />
      </View>

      <FlatList
        data={sessions}
        keyExtractor={(s) => s.session_id}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeInDown.delay(index * 50)}>
            <TouchableOpacity style={styles.card} activeOpacity={0.7}>
              <View style={[styles.triagePill, { backgroundColor: TRIAGE_COLORS[item.triage_level] + '20' }]}>
                <Text style={[styles.triageLabel, { color: TRIAGE_COLORS[item.triage_level] }]}>
                  {TRIAGE_LABELS[item.triage_level]}
                </Text>
              </View>
              <View style={styles.body}>
                <Text style={styles.diagnosis}>{item.primary_diagnosis}</Text>
                {item.red_flags?.length > 0 && (
                  <Text style={styles.redFlags}>⚠ {item.red_flags.join(', ')}</Text>
                )}
                <Text style={styles.meta}>{item.language} · {item.duration}</Text>
              </View>
              <Text style={styles.arrow}>→</Text>
            </TouchableOpacity>
          </Animated.View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>{isLoading ? 'Loading...' : 'No patients in queue'}</Text>
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
  triagePill: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.pill,
  },
  triageLabel: { ...TYPE.micro, fontWeight: '700' },
  body: { flex: 1, gap: 4 },
  diagnosis: { ...TYPE.titleMed, color: COLORS.ink },
  redFlags: { ...TYPE.micro, color: COLORS.crimson, fontWeight: '600' },
  meta: { ...TYPE.micro, color: COLORS.textMuted },
  arrow: { fontSize: 14, color: COLORS.textFaint },
  empty: { alignItems: 'center', paddingVertical: 48 },
  emptyText: { ...TYPE.bodyMed, color: COLORS.textMuted },
});
