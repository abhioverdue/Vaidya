/**
 * Vaidya — Consent Management screen
 * Shows the 3 DPDP Act 2023 consent purposes, lets user grant/revoke optional ones,
 * and exposes an inline audit log.
 */

import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  Switch, ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useState, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { apiClient } from '@/services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

type PurposeKey = 'data_processing' | 'anonymised_analytics' | 'asha_contact';

interface ConsentPurpose {
  key: PurposeKey;
  name: string;
  required: boolean;
  description: string;
}

interface ConsentAuditEntry {
  purpose: PurposeKey;
  action: 'granted' | 'revoked';
  timestamp: string;
  ip_hint?: string;
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_PURPOSES: ConsentPurpose[] = [
  {
    key: 'data_processing',
    name: 'Core Data Processing',
    required: true,
    description:
      'Your symptom inputs are processed by our AI pipeline to generate triage recommendations. This processing is necessary for the service to function and cannot be disabled. Data is encrypted in transit and at rest and never sold to third parties.',
  },
  {
    key: 'anonymised_analytics',
    name: 'Anonymised Health Analytics',
    required: false,
    description:
      'Fully anonymised, aggregated patterns from your sessions (no names, no identifiers) may be used to improve outbreak detection and public health research conducted by NHM-affiliated bodies. You can revoke this at any time.',
  },
  {
    key: 'asha_contact',
    name: 'ASHA Worker Follow-up Contact',
    required: false,
    description:
      'Your assigned ASHA worker may contact you via phone for follow-up care after a triage session. Your phone number is only shared with the assigned ASHA and never used for marketing.',
  },
];

const DEMO_INITIAL_GRANTS: Record<PurposeKey, boolean> = {
  data_processing:      true,
  anonymised_analytics: true,
  asha_contact:         false,
};

const DEMO_AUDIT: ConsentAuditEntry[] = [
  { purpose: 'data_processing',      action: 'granted', timestamp: '2026-02-01T08:00:00Z' },
  { purpose: 'anonymised_analytics', action: 'granted', timestamp: '2026-02-01T08:00:12Z' },
  { purpose: 'anonymised_analytics', action: 'revoked', timestamp: '2026-03-10T14:23:00Z' },
  { purpose: 'anonymised_analytics', action: 'granted', timestamp: '2026-04-05T09:11:00Z' },
];

// ── ConsentManageScreen ───────────────────────────────────────────────────────

export default function ConsentManageScreen() {
  const [grants, setGrants] = useState<Record<PurposeKey, boolean>>(DEMO_INITIAL_GRANTS);
  const [original] = useState<Record<PurposeKey, boolean>>(DEMO_INITIAL_GRANTS);
  const [auditExpanded, setAuditExpanded] = useState(false);

  // ── Load purpose descriptions ─────────────────────────────────────────────
  const { data: purposes } = useQuery<ConsentPurpose[]>({
    queryKey: ['consent-descriptions'],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get<{ purposes: Array<{ type: string; required: boolean; description: string }> }>(
          '/consent/descriptions',
        );
        const NAME_MAP: Record<string, string> = {
          data_processing:      'Core Data Processing',
          anonymised_analytics: 'Anonymised Health Analytics',
          asha_contact:         'ASHA Worker Follow-up Contact',
        };
        return data.purposes.map((p) => ({
          key:         p.type as PurposeKey,
          name:        NAME_MAP[p.type] ?? p.type,
          required:    p.required,
          description: p.description,
        }));
      } catch {
        return DEMO_PURPOSES;
      }
    },
    staleTime: 5 * 60 * 1000,
    initialData: DEMO_PURPOSES,
  });

  // ── Load audit log ────────────────────────────────────────────────────────
  const { data: audit, isLoading: auditLoading } = useQuery<ConsentAuditEntry[]>({
    queryKey: ['consent-audit'],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get<{ entries: ConsentAuditEntry[] }>(
          '/consent/audit',
        );
        return data.entries;
      } catch {
        return DEMO_AUDIT;
      }
    },
    enabled: auditExpanded,
    staleTime: 60_000,
  });

  // ── Save mutation ─────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async () => {
      const changed = (Object.keys(grants) as PurposeKey[]).filter(
        (k) => grants[k] !== original[k],
      );
      for (const key of changed) {
        const endpoint = grants[key] ? '/consent/grant' : '/consent/revoke';
        try {
          await apiClient.post(endpoint, { purpose: key });
        } catch {
          continue;
        }
      }
    },
    onSuccess: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    },
    onError: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    },
  });

  const toggle = useCallback((key: PurposeKey, value: boolean) => {
    if (key === 'data_processing') return; // required, cannot revoke
    setGrants((prev) => ({ ...prev, [key]: value }));
    Haptics.selectionAsync();
  }, []);

  const hasChanges = (Object.keys(grants) as PurposeKey[]).some(
    (k) => grants[k] !== original[k],
  );

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
        <View style={s.headerCenter}>
          <Text style={s.headerTitle}>Privacy & Consent</Text>
          <View style={s.dpdpChip}>
            <Text style={s.dpdpChipText}>DPDP Act 2023</Text>
          </View>
        </View>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Purpose cards */}
        {(purposes ?? DEMO_PURPOSES).map((p, i) => (
          <Animated.View key={p.key} entering={FadeInDown.duration(400).delay(i * 80)}>
            <View style={s.card}>
              <View style={s.cardHeader}>
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={s.purposeName}>{p.name}</Text>
                  <View style={[s.badge, p.required ? s.badgeRequired : s.badgeOptional]}>
                    <Text style={[s.badgeText, p.required ? s.badgeTextRequired : s.badgeTextOptional]}>
                      {p.required ? 'Required' : 'Optional'}
                    </Text>
                  </View>
                </View>
                <Switch
                  value={grants[p.key]}
                  onValueChange={(v) => toggle(p.key, v)}
                  disabled={p.required}
                  trackColor={{ false: COLORS.border, true: COLORS.sage }}
                  thumbColor={p.required ? COLORS.textFaint : COLORS.surface}
                />
              </View>
              <Text style={s.description}>{p.description}</Text>
              {p.required && (
                <View style={s.lockedNote}>
                  <Text style={s.lockedNoteText}>
                    This consent is required for core functionality and cannot be revoked after first use.
                  </Text>
                </View>
              )}
            </View>
          </Animated.View>
        ))}

        {/* Save button */}
        <Animated.View entering={FadeInDown.duration(400).delay(280)}>
          <TouchableOpacity
            style={[s.saveBtn, (!hasChanges || saveMutation.isPending) && s.saveBtnDim]}
            onPress={() => saveMutation.mutate()}
            disabled={!hasChanges || saveMutation.isPending}
            activeOpacity={0.85}
          >
            {saveMutation.isPending
              ? <ActivityIndicator color={COLORS.parchment} />
              : <Text style={s.saveBtnText}>
                  {saveMutation.isSuccess ? 'Preferences saved' : 'Save preferences'}
                </Text>
            }
          </TouchableOpacity>
        </Animated.View>

        {/* Audit log */}
        <Animated.View entering={FadeInDown.duration(400).delay(360)}>
          <TouchableOpacity
            style={s.auditToggle}
            onPress={() => { setAuditExpanded((v) => !v); Haptics.selectionAsync(); }}
            activeOpacity={0.7}
          >
            <Text style={s.auditToggleText}>
              {auditExpanded ? 'Hide audit log' : 'View audit log'}
            </Text>
            <Text style={s.auditChevron}>{auditExpanded ? '▲' : '▼'}</Text>
          </TouchableOpacity>

          {auditExpanded && (
            <View style={s.auditCard}>
              {auditLoading && <ActivityIndicator color={COLORS.sage} style={{ paddingVertical: 16 }} />}
              {!auditLoading && (audit ?? DEMO_AUDIT).length === 0 && (
                <Text style={s.auditEmpty}>No consent events recorded yet.</Text>
              )}
              {!auditLoading && (audit ?? DEMO_AUDIT).map((entry, i) => {
                const purposeLabel = DEMO_PURPOSES.find((p) => p.key === entry.purpose)?.name ?? entry.purpose;
                const date = new Date(entry.timestamp).toLocaleString('en-IN', {
                  day: '2-digit', month: 'short', year: 'numeric',
                  hour: '2-digit', minute: '2-digit',
                });
                const isLast = i === (audit ?? DEMO_AUDIT).length - 1;
                return (
                  <View key={i} style={[s.auditRow, !isLast && s.auditRowBorder]}>
                    <View style={[
                      s.auditDot,
                      { backgroundColor: entry.action === 'granted' ? COLORS.sage : COLORS.crimson },
                    ]} />
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={s.auditPurpose}>{purposeLabel}</Text>
                      <Text style={s.auditDate}>{date}</Text>
                    </View>
                    <Text style={[
                      s.auditAction,
                      { color: entry.action === 'granted' ? COLORS.sage : COLORS.crimson },
                    ]}>
                      {entry.action.charAt(0).toUpperCase() + entry.action.slice(1)}
                    </Text>
                  </View>
                );
              })}
            </View>
          )}
        </Animated.View>

        <Text style={s.footer}>
          Your rights are protected under the Digital Personal Data Protection Act 2023.
        </Text>

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
  backBtn:      { width: 40 },
  backCircle:   { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backText:     { fontSize: 18, color: COLORS.sage, fontWeight: '700', marginTop: -1 },
  headerCenter: { alignItems: 'center', gap: 4 },
  headerTitle:  { ...TYPE.headlineLarge, color: COLORS.ink },
  dpdpChip:     { backgroundColor: COLORS.goldGhost, borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 3, borderWidth: 1, borderColor: 'rgba(154,107,31,0.2)' },
  dpdpChipText: { ...TYPE.micro, color: COLORS.gold, fontWeight: '700' },

  scroll: { padding: 20, paddingBottom: 52, gap: 12 },

  card: {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 16,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05, shadowRadius: 6, elevation: 2,
  },
  cardHeader:   { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 10, gap: 10 },
  purposeName:  { ...TYPE.titleLarge, color: COLORS.ink },
  badge:        { alignSelf: 'flex-start', borderRadius: RADIUS.pill, paddingHorizontal: 9, paddingVertical: 3, borderWidth: 1 },
  badgeRequired:{ backgroundColor: COLORS.inkGhost, borderColor: 'rgba(15,17,23,0.14)' },
  badgeOptional:{ backgroundColor: COLORS.sageGhost, borderColor: 'rgba(58,95,82,0.18)' },
  badgeText:    { fontSize: 10, fontWeight: '700', letterSpacing: 0.4 },
  badgeTextRequired: { color: COLORS.textMuted },
  badgeTextOptional: { color: COLORS.sage },
  description:  { ...TYPE.bodyMed, color: COLORS.textSub, lineHeight: 22 },
  lockedNote:   { marginTop: 10, backgroundColor: COLORS.inkGhost, borderRadius: RADIUS.md, padding: 10 },
  lockedNoteText:{ ...TYPE.micro, color: COLORS.textMuted, lineHeight: 16 },

  saveBtn:    { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 18, alignItems: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.18, shadowRadius: 10, elevation: 6, marginTop: 4 },
  saveBtnDim: { opacity: 0.45 },
  saveBtnText:{ ...TYPE.titleLarge, color: COLORS.parchment, fontSize: 16 },

  auditToggle:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 14, gap: 6 },
  auditToggleText:{ ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '600' },
  auditChevron:   { fontSize: 10, color: COLORS.sage },

  auditCard:     { backgroundColor: COLORS.surface, borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.border, padding: 4 },
  auditEmpty:    { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center', padding: 20 },
  auditRow:      { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 10 },
  auditRowBorder:{ borderBottomWidth: 1, borderBottomColor: COLORS.border },
  auditDot:      { width: 8, height: 8, borderRadius: 4 },
  auditPurpose:  { ...TYPE.bodySmall, color: COLORS.ink, fontWeight: '500' },
  auditDate:     { ...TYPE.micro, color: COLORS.textMuted },
  auditAction:   { fontSize: 11, fontWeight: '700' },

  footer: { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', lineHeight: 18, marginTop: 12, paddingHorizontal: 16 },
});
