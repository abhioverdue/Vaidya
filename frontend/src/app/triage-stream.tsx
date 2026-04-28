/**
 * Vaidya — Live Triage Stream  (Module 9)
 * Real-time SSE stream of triage sessions for health officer dashboard
 */

import {
  View, Text, FlatList, StyleSheet, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useEffect, useState, useRef } from 'react';
import Animated, { FadeInRight } from 'react-native-reanimated';

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

const DEMO_POOL = [
  { triage_level: 4, primary_diagnosis: 'Dengue Fever (suspected)', red_flags: ['High fever', 'Rash'], input_language: 'ta', asha_assigned: { name: 'Meena Devi' } },
  { triage_level: 2, primary_diagnosis: 'Viral Upper Respiratory Infection', red_flags: [], input_language: 'ta', asha_assigned: null },
  { triage_level: 3, primary_diagnosis: 'Acute Gastroenteritis', red_flags: ['Dehydration risk'], input_language: 'hi', asha_assigned: { name: 'Lakshmi Bai' } },
  { triage_level: 1, primary_diagnosis: 'Tension Headache', red_flags: [], input_language: 'en', asha_assigned: null },
  { triage_level: 3, primary_diagnosis: 'Hypertension (uncontrolled)', red_flags: ['BP 160/100'], input_language: 'ta', asha_assigned: { name: 'Saraswathi R.' } },
  { triage_level: 2, primary_diagnosis: 'Iron Deficiency Anaemia', red_flags: [], input_language: 'ta', asha_assigned: null },
  { triage_level: 4, primary_diagnosis: 'Malaria (P. vivax suspected)', red_flags: ['Cyclic fever', 'Chills'], input_language: 'hi', asha_assigned: { name: 'Kamala Selvam' } },
  { triage_level: 1, primary_diagnosis: 'Acid Reflux (GERD)', red_flags: [], input_language: 'en', asha_assigned: null },
  { triage_level: 3, primary_diagnosis: 'Type 2 Diabetes (uncontrolled)', red_flags: ['High glucose'], input_language: 'ta', asha_assigned: null },
  { triage_level: 2, primary_diagnosis: 'Urinary Tract Infection', red_flags: [], input_language: 'ta', asha_assigned: { name: 'Valli Krishnan' } },
];

let _poolIndex = 0;

function makeDemoEvent() {
  const base = DEMO_POOL[_poolIndex % DEMO_POOL.length];
  _poolIndex += 1;
  return { ...base, created_at: new Date().toISOString() };
}

export default function TriageStreamScreen() {
  const { t } = useTranslation();
  const [stream, setStream] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Seed with a few initial events so the list isn't empty
    const seed = Array.from({ length: 4 }, () => makeDemoEvent());
    setStream(seed);
    setConnected(true);

    // Simulate live events arriving every 6–12 seconds
    timerRef.current = setInterval(() => {
      setStream((prev) => [makeDemoEvent(), ...prev].slice(0, 50));
    }, 8000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const handleRefresh = () => {
    setStream([]);
    setConnected(false);
    setTimeout(() => {
      const seed = Array.from({ length: 4 }, () => makeDemoEvent());
      setStream(seed);
      setConnected(true);
    }, 800);
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <OfflineBanner />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backBtn}>← Back</Text>
        </TouchableOpacity>
        <SectionHeader title="Live Triage Stream" subtitle="Real-time sessions" />
      </View>

      {/* Connection Status */}
      <View style={[styles.statusBar, { backgroundColor: connected ? COLORS.sageGhost : COLORS.parchmentWarm }]}>
        <View style={[styles.statusDot, { backgroundColor: connected ? COLORS.sage : COLORS.crimson }]} />
        <Text style={[styles.statusText, { color: connected ? COLORS.sage : COLORS.crimson }]}>
          {connected ? '● Live' : error ? '● Error' : '● Connecting...'}
        </Text>
        {error && <Text style={styles.errorText}>{error}</Text>}
      </View>

      <FlatList
        data={stream}
        keyExtractor={(item, idx) => idx.toString()}
        refreshControl={<RefreshControl refreshing={!connected} onRefresh={handleRefresh} />}
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeInRight.delay(index * 30)}>
            <View style={styles.sessionCard}>
              <View style={styles.sessionTop}>
                <View style={[styles.triagePill, { backgroundColor: TRIAGE_COLORS[item.triage_level] + '20' }]}>
                  <Text style={[styles.triageLabel, { color: TRIAGE_COLORS[item.triage_level] }]}>
                    {TRIAGE_LABELS[item.triage_level]}
                  </Text>
                </View>
                <Text style={styles.timestamp}>{new Date(item.created_at).toLocaleTimeString()}</Text>
              </View>
              <Text style={styles.diagnosis}>{item.primary_diagnosis}</Text>
              {item.red_flags?.length > 0 && (
                <Text style={styles.redFlags}>⚠ {item.red_flags.join(', ')}</Text>
              )}
              <View style={styles.footer}>
                <Text style={styles.lang}>{item.input_language.toUpperCase()}</Text>
                {item.asha_assigned && (
                  <Text style={styles.assigned}>→ {item.asha_assigned.name}</Text>
                )}
              </View>
            </View>
          </Animated.View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            {connected ? (
              <>
                <Text style={styles.emptyText}>Waiting for sessions...</Text>
                <Text style={styles.emptySubText}>New triage sessions will appear here</Text>
              </>
            ) : (
              <>
                <ActivityIndicator size="large" color={COLORS.ink} />
                <Text style={styles.emptyText}>Connecting to stream...</Text>
              </>
            )}
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
  statusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    marginHorizontal: 16,
    borderRadius: RADIUS.lg,
    marginBottom: 12,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { ...TYPE.bodySmall, fontWeight: '700' },
  errorText: { ...TYPE.micro, marginLeft: 'auto' },
  sessionCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 12,
    borderLeftWidth: 3,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 6,
  },
  sessionTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  triagePill: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: RADIUS.pill,
  },
  triageLabel: { ...TYPE.micro, fontWeight: '700' },
  timestamp: { ...TYPE.micro, color: COLORS.textFaint },
  diagnosis: { ...TYPE.titleMed, color: COLORS.ink },
  redFlags: { ...TYPE.micro, color: COLORS.crimson, fontWeight: '600' },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  lang: { ...TYPE.micro, color: COLORS.textMuted, fontWeight: '700' },
  assigned: { ...TYPE.micro, color: COLORS.sage, fontWeight: '600' },
  empty: { alignItems: 'center', paddingVertical: 80, gap: 12 },
  emptyText: { ...TYPE.titleMed, color: COLORS.textMuted },
  emptySubText: { ...TYPE.micro, color: COLORS.textFaint },
});
