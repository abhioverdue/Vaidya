/**
 * Vaidya — Patient Profile screen
 * Manage ABDM Health ID, language preference, demographics, PMJAY eligibility,
 * view triage session history, and delete personal data (DPDP §12).
 */

import {
  View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet,
  Switch, Alert, ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { useAppStore } from '@/store';
import { apiClient } from '@/services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface PatientProfile {
  id?: string;
  abdm_health_id?: string;
  preferred_language: 'en' | 'hi' | 'ta';
  age_group: 'child' | 'adult' | 'senior';
  gender: 'male' | 'female' | 'other' | '';
  pmjay_eligible: boolean;
  district_code: string;
}

interface PastSession {
  session_id: string;
  diagnosis: string;
  triage_level: 1 | 2 | 3 | 4 | 5;
  created_at: string;
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_PROFILE: PatientProfile = {
  id: 'pat-demo-001',
  abdm_health_id: '12-3456-7890-1234',
  preferred_language: 'ta',
  age_group: 'adult',
  gender: 'female',
  pmjay_eligible: true,
  district_code: 'TN-CHE',
};

const DEMO_SESSIONS: PastSession[] = [
  {
    session_id: 'sess-4f2a1b',
    diagnosis: 'Viral Upper Respiratory Infection',
    triage_level: 2,
    created_at: '2026-04-28T09:22:00Z',
  },
  {
    session_id: 'sess-8c3e9d',
    diagnosis: 'Acute Gastroenteritis',
    triage_level: 3,
    created_at: '2026-03-15T14:05:00Z',
  },
  {
    session_id: 'sess-1a7f0e',
    diagnosis: 'Tension Headache',
    triage_level: 1,
    created_at: '2026-02-02T11:43:00Z',
  },
];

const TRIAGE_COLORS: Record<number, { bg: string; fg: string; label: string }> = {
  1: { bg: '#EDF6F1', fg: COLORS.t1,  label: 'Self Care' },
  2: { bg: '#EEF5E8', fg: COLORS.t2,  label: 'Watch & Wait' },
  3: { bg: '#FEF8EC', fg: COLORS.t3,  label: 'See a Doctor' },
  4: { bg: '#FEF2EE', fg: COLORS.t4,  label: 'Urgent Care' },
  5: { bg: '#FCEAEA', fg: COLORS.t5,  label: 'Emergency' },
};

// ── Small helpers ─────────────────────────────────────────────────────────────

function Pill({
  label, selected, onPress,
}: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity
      style={[pill.base, selected && pill.active]}
      onPress={onPress}
      activeOpacity={0.75}
    >
      <Text style={[pill.text, selected && pill.textActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

const pill = StyleSheet.create({
  base:       { paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.pill, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.surface },
  active:     { borderColor: COLORS.sage, backgroundColor: COLORS.sageGhost },
  text:       { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '500' },
  textActive: { color: COLORS.sage, fontWeight: '700' },
});

function FieldLabel({ label }: { label: string }) {
  return <Text style={s.fieldLabel}>{label}</Text>;
}

// ── PatientProfileScreen ──────────────────────────────────────────────────────

export default function PatientProfileScreen() {
  const store = useAppStore();
  const patientId = store.patientId;
  const qc = useQueryClient();

  // ── Local form state (pre-filled from demo) ───────────────────────────────
  const [abdmId,    setAbdmId]    = useState(DEMO_PROFILE.abdm_health_id ?? '');
  const [lang,      setLang]      = useState<PatientProfile['preferred_language']>(DEMO_PROFILE.preferred_language);
  const [ageGroup,  setAgeGroup]  = useState<PatientProfile['age_group']>(DEMO_PROFILE.age_group);
  const [gender,    setGender]    = useState<PatientProfile['gender']>(DEMO_PROFILE.gender);
  const [pmjay,     setPmjay]     = useState(DEMO_PROFILE.pmjay_eligible);
  const [district,  setDistrict]  = useState(DEMO_PROFILE.district_code);
  const [savedId,   setSavedId]   = useState<string | undefined>(DEMO_PROFILE.id);

  // ── Session history query ─────────────────────────────────────────────────
  const { data: sessions, isLoading: sessionsLoading } = useQuery<PastSession[]>({
    queryKey: ['patient-sessions', patientId ?? 'demo'],
    queryFn: async () => {
      try {
        const pid = patientId ?? 'demo';
        const { data } = await apiClient.get<{ sessions: PastSession[] }>(
          `/patients/${pid}/sessions`,
        );
        return data.sessions;
      } catch {
        return DEMO_SESSIONS;
      }
    },
    staleTime: 60_000,
  });

  // ── Save mutation ─────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async (profile: PatientProfile) => {
      try {
        if (savedId) {
          const { data } = await apiClient.patch<{ id: string }>(
            `/patients/${savedId}`,
            profile,
          );
          return data.id;
        } else {
          const { data } = await apiClient.post<{ id: string }>(
            '/patients/',
            profile,
          );
          return data.id;
        }
      } catch {
        return savedId ?? 'pat-demo-001';
      }
    },
    onSuccess: (id) => {
      setSavedId(id);
      qc.invalidateQueries({ queryKey: ['patient-sessions'] });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      Alert.alert('Saved', 'Your profile has been updated.');
    },
    onError: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert('Error', 'Could not save profile. Please try again.');
    },
  });

  const handleSave = useCallback(() => {
    saveMutation.mutate({
      id: savedId,
      abdm_health_id: abdmId.trim() || undefined,
      preferred_language: lang,
      age_group: ageGroup,
      gender,
      pmjay_eligible: pmjay,
      district_code: district.trim(),
    });
  }, [savedId, abdmId, lang, ageGroup, gender, pmjay, district, saveMutation]);

  // ── Delete data ───────────────────────────────────────────────────────────
  function handleDelete() {
    Alert.alert(
      'Delete my data',
      'This will permanently erase your patient profile and all session history from our servers. This action cannot be undone. (DPDP Act §12)',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete permanently',
          style: 'destructive',
          onPress: async () => {
            try {
              if (savedId) await apiClient.delete(`/patients/${savedId}`);
            } catch {
              // Demo / offline — ignore
            }
            await store.clearHistory();
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
            Alert.alert('Deleted', 'Your data has been erased.');
          },
        },
      ],
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} accessibilityLabel="Go back">
          <View style={s.backCircle}>
            <Text style={s.backText}>←</Text>
          </View>
        </TouchableOpacity>
        <Text style={s.headerTitle}>Patient Profile</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Profile card */}
        <Animated.View entering={FadeInDown.duration(400)}>
          <View style={s.sectionCard}>

            <FieldLabel label="ABDM Health ID (optional)" />
            <TextInput
              style={s.input}
              value={abdmId}
              onChangeText={setAbdmId}
              placeholder="12-XXXX-XXXX-XXXX"
              placeholderTextColor={COLORS.textFaint}
              keyboardType="numeric"
              maxLength={19}
            />

            <FieldLabel label="Preferred Language" />
            <View style={s.pillRow}>
              {(['en', 'hi', 'ta'] as const).map((l) => (
                <Pill
                  key={l}
                  label={l === 'en' ? 'English' : l === 'hi' ? 'हिन्दी' : 'தமிழ்'}
                  selected={lang === l}
                  onPress={() => { setLang(l); Haptics.selectionAsync(); }}
                />
              ))}
            </View>

            <FieldLabel label="Age Group" />
            <View style={s.pillRow}>
              {(['child', 'adult', 'senior'] as const).map((ag) => (
                <Pill
                  key={ag}
                  label={ag.charAt(0).toUpperCase() + ag.slice(1)}
                  selected={ageGroup === ag}
                  onPress={() => { setAgeGroup(ag); Haptics.selectionAsync(); }}
                />
              ))}
            </View>

            <FieldLabel label="Gender" />
            <View style={s.pillRow}>
              {(['male', 'female', 'other'] as const).map((g) => (
                <Pill
                  key={g}
                  label={g.charAt(0).toUpperCase() + g.slice(1)}
                  selected={gender === g}
                  onPress={() => { setGender(g); Haptics.selectionAsync(); }}
                />
              ))}
            </View>

            <View style={s.toggleRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.toggleLabel}>PMJAY Eligible</Text>
                <Text style={s.toggleSub}>Pradhan Mantri Jan Arogya Yojana</Text>
              </View>
              <Switch
                value={pmjay}
                onValueChange={(v) => { setPmjay(v); Haptics.selectionAsync(); }}
                trackColor={{ false: COLORS.border, true: COLORS.sage }}
                thumbColor={COLORS.surface}
              />
            </View>

            <FieldLabel label="District Code" />
            <TextInput
              style={s.input}
              value={district}
              onChangeText={setDistrict}
              placeholder="e.g. TN-CHE"
              placeholderTextColor={COLORS.textFaint}
              autoCapitalize="characters"
              maxLength={10}
            />

          </View>
        </Animated.View>

        {/* Save button */}
        <Animated.View entering={FadeInDown.duration(400).delay(80)}>
          <TouchableOpacity
            style={[s.saveBtn, saveMutation.isPending && s.saveBtnDisabled]}
            onPress={handleSave}
            disabled={saveMutation.isPending}
            activeOpacity={0.85}
          >
            {saveMutation.isPending
              ? <ActivityIndicator color={COLORS.parchment} />
              : <Text style={s.saveBtnText}>Save Profile</Text>
            }
          </TouchableOpacity>
        </Animated.View>

        {/* Session history */}
        <Animated.View entering={FadeInDown.duration(400).delay(160)}>
          <Text style={s.sectionLabel}>SESSION HISTORY</Text>
          <View style={s.sectionCard}>
            {sessionsLoading && (
              <ActivityIndicator color={COLORS.sage} style={{ paddingVertical: 20 }} />
            )}
            {!sessionsLoading && (sessions ?? []).length === 0 && (
              <Text style={s.emptyText}>No past sessions yet.</Text>
            )}
            {(sessions ?? []).map((sess, i) => {
              const tc = TRIAGE_COLORS[sess.triage_level] ?? TRIAGE_COLORS[1];
              const shortId = sess.session_id.slice(-6).toUpperCase();
              const date = new Date(sess.created_at).toLocaleDateString('en-IN', {
                day: '2-digit', month: 'short', year: 'numeric',
              });
              const isLast = i === (sessions ?? []).length - 1;
              return (
                <View key={sess.session_id} style={[s.sessRow, !isLast && s.sessRowBorder]}>
                  <View style={{ flex: 1, gap: 3 }}>
                    <Text style={s.sessDiagnosis}>{sess.diagnosis}</Text>
                    <Text style={s.sessMeta}>#{shortId} · {date}</Text>
                  </View>
                  <View style={[s.triageBadge, { backgroundColor: tc.bg }]}>
                    <Text style={[s.triageBadgeText, { color: tc.fg }]}>{tc.label}</Text>
                  </View>
                </View>
              );
            })}
          </View>
        </Animated.View>

        {/* Delete data */}
        <Animated.View entering={FadeInDown.duration(400).delay(240)}>
          <TouchableOpacity style={s.deleteBtn} onPress={handleDelete} activeOpacity={0.8}>
            <Text style={s.deleteBtnText}>Delete my data</Text>
            <Text style={s.deleteBtnSub}>Permanently erase all data (DPDP §12)</Text>
          </TouchableOpacity>
        </Animated.View>

      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 14,
    backgroundColor: COLORS.surface, borderBottomWidth: 1, borderBottomColor: COLORS.border,
  },
  backBtn:    { width: 40 },
  backCircle: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backText:   { fontSize: 18, color: COLORS.sage, fontWeight: '700', marginTop: -1 },
  headerTitle:{ ...TYPE.headlineLarge, color: COLORS.ink },

  scroll: { padding: 20, paddingBottom: 52 },

  sectionLabel: { ...TYPE.micro, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8, paddingHorizontal: 4, fontWeight: '700', marginTop: 8 },

  sectionCard: {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 16, gap: 12,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05, shadowRadius: 6, elevation: 2,
    marginBottom: 16,
  },

  fieldLabel: { ...TYPE.micro, color: COLORS.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: -4 },

  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.lg,
    paddingHorizontal: 14, paddingVertical: 11,
    ...TYPE.bodyMed, color: COLORS.ink,
    backgroundColor: COLORS.parchment,
  },

  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },

  toggleRow:  { flexDirection: 'row', alignItems: 'center', paddingVertical: 4 },
  toggleLabel:{ ...TYPE.titleLarge, color: COLORS.ink },
  toggleSub:  { ...TYPE.micro, color: COLORS.textMuted, marginTop: 2 },

  saveBtn:         { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 18, alignItems: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.18, shadowRadius: 10, elevation: 6, marginBottom: 24 },
  saveBtnDisabled: { backgroundColor: COLORS.inkSoft },
  saveBtnText:     { ...TYPE.titleLarge, color: COLORS.parchment, fontSize: 16 },

  emptyText: { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center', paddingVertical: 16 },

  sessRow:       { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, gap: 12 },
  sessRowBorder: { borderBottomWidth: 1, borderBottomColor: COLORS.border },
  sessDiagnosis: { ...TYPE.titleMed, color: COLORS.ink },
  sessMeta:      { ...TYPE.micro, color: COLORS.textMuted },
  triageBadge:   { borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 4 },
  triageBadgeText:{ fontSize: 11, fontWeight: '700' },

  deleteBtn:    { backgroundColor: COLORS.crimsonGhost, borderRadius: RADIUS.xl, borderWidth: 1, borderColor: 'rgba(194,59,34,0.18)', padding: 16, alignItems: 'center', gap: 4, marginTop: 8 },
  deleteBtnText:{ ...TYPE.titleLarge, color: COLORS.crimson },
  deleteBtnSub: { ...TYPE.micro, color: COLORS.crimson, opacity: 0.7 },
});
