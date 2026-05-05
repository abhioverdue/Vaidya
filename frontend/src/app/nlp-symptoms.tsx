/**
 * Vaidya — NLP Symptom Explorer screen
 * Search symptoms, extract from free text, and build a selected-symptom set.
 */

import {
  View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet,
  ActivityIndicator, Keyboard,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { apiClient } from '@/services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SymptomItem {
  id: string;
  name: string;
  icd_hint?: string;
}

interface SearchResult {
  symptom: SymptomItem;
  score: number;
}

interface ExtractResult {
  symptoms: SymptomItem[];
  duration?: string;
  severity_estimate: number;
  body_parts: string[];
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_ALL_SYMPTOMS: SymptomItem[] = [
  { id: 's01', name: 'Fever',            icd_hint: 'R50' },
  { id: 's02', name: 'Cough',            icd_hint: 'R05' },
  { id: 's03', name: 'Headache',         icd_hint: 'R51' },
  { id: 's04', name: 'Vomiting',         icd_hint: 'R11' },
  { id: 's05', name: 'Diarrhoea',        icd_hint: 'A09' },
  { id: 's06', name: 'Chest pain',       icd_hint: 'R07' },
  { id: 's07', name: 'Breathlessness',   icd_hint: 'R06' },
  { id: 's08', name: 'Body ache',        icd_hint: 'M79' },
  { id: 's09', name: 'Rash',             icd_hint: 'R21' },
  { id: 's10', name: 'Fatigue',          icd_hint: 'R53' },
  { id: 's11', name: 'Sore throat',      icd_hint: 'J02' },
  { id: 's12', name: 'Runny nose',       icd_hint: 'J30' },
  { id: 's13', name: 'Abdominal pain',   icd_hint: 'R10' },
  { id: 's14', name: 'Joint pain',       icd_hint: 'M25' },
  { id: 's15', name: 'Nausea',           icd_hint: 'R11' },
  { id: 's16', name: 'Dizziness',        icd_hint: 'R42' },
  { id: 's17', name: 'Eye redness',      icd_hint: 'H10' },
  { id: 's18', name: 'Skin itching',     icd_hint: 'L29' },
  { id: 's19', name: 'Loss of appetite', icd_hint: 'R63' },
  { id: 's20', name: 'Neck stiffness',   icd_hint: 'M54' },
  { id: 's21', name: 'Ear pain',         icd_hint: 'H92' },
  { id: 's22', name: 'Painful urination',icd_hint: 'R30' },
  { id: 's23', name: 'Palpitations',     icd_hint: 'R00' },
  { id: 's24', name: 'Jaundice',         icd_hint: 'R17' },
];

function demoSearch(q: string): SearchResult[] {
  const query = q.toLowerCase();
  return DEMO_ALL_SYMPTOMS
    .filter((s) => s.name.toLowerCase().includes(query))
    .slice(0, 8)
    .map((s) => ({
      symptom: s,
      score: s.name.toLowerCase().startsWith(query) ? 0.95 : 0.72,
    }));
}

const DEMO_EXTRACT: ExtractResult = {
  symptoms: [
    DEMO_ALL_SYMPTOMS[0], // Fever
    DEMO_ALL_SYMPTOMS[1], // Cough
    DEMO_ALL_SYMPTOMS[10],// Sore throat
  ],
  duration: '3 days',
  severity_estimate: 5,
  body_parts: ['throat', 'chest', 'head'],
};

// ── ScoreBar ──────────────────────────────────────────────────────────────────

function ScoreBar({ score }: { score: number }) {
  return (
    <View style={bar.track}>
      <View style={[bar.fill, { width: `${Math.round(score * 100)}%` as any }]} />
    </View>
  );
}

const bar = StyleSheet.create({
  track: { flex: 1, height: 4, backgroundColor: COLORS.border, borderRadius: 2, overflow: 'hidden' },
  fill:  { height: '100%', backgroundColor: COLORS.sage, borderRadius: 2 },
});

// ── Chip ──────────────────────────────────────────────────────────────────────

function Chip({
  label, selected, onPress, small,
}: { label: string; selected?: boolean; onPress: () => void; small?: boolean }) {
  return (
    <TouchableOpacity
      style={[chip.base, small && chip.small, selected && chip.selected]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Text style={[chip.text, small && chip.textSmall, selected && chip.textSelected]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const chip = StyleSheet.create({
  base:         { paddingHorizontal: 12, paddingVertical: 7, borderRadius: RADIUS.pill, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.surface },
  small:        { paddingHorizontal: 10, paddingVertical: 5 },
  selected:     { borderColor: COLORS.sage, backgroundColor: COLORS.sageGhost },
  text:         { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '500' },
  textSmall:    { fontSize: 11 },
  textSelected: { color: COLORS.sage, fontWeight: '700' },
});

// ── SeverityBar ───────────────────────────────────────────────────────────────

function SeverityBar({ value }: { value: number }) {
  const color = value <= 3 ? COLORS.sage : value <= 6 ? COLORS.gold : COLORS.crimson;
  return (
    <View style={sev.wrap}>
      <View style={sev.track}>
        <View style={[sev.fill, { width: `${value * 10}%` as any, backgroundColor: color }]} />
      </View>
      <Text style={[sev.label, { color }]}>{value}/10</Text>
    </View>
  );
}

const sev = StyleSheet.create({
  wrap:  { flexDirection: 'row', alignItems: 'center', gap: 8 },
  track: { flex: 1, height: 6, backgroundColor: COLORS.border, borderRadius: 3, overflow: 'hidden' },
  fill:  { height: '100%', borderRadius: 3 },
  label: { fontSize: 12, fontWeight: '700', minWidth: 28 },
});

// ── NlpSymptomsScreen ─────────────────────────────────────────────────────────

export default function NlpSymptomsScreen() {
  const [searchQ,   setSearchQ]   = useState('');
  const [debouncedQ,setDebouncedQ]= useState('');
  const [extractText,setExtractText]=useState('');
  const [selected, setSelected]   = useState<Set<string>>(new Set());
  const [extractResult, setExtractResult] = useState<ExtractResult | null>(null);

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search input
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => setDebouncedQ(searchQ.trim()), 300);
    return () => { if (debounceTimer.current) clearTimeout(debounceTimer.current); };
  }, [searchQ]);

  // ── All symptoms query ────────────────────────────────────────────────────
  const { data: allSymptoms } = useQuery<SymptomItem[]>({
    queryKey: ['nlp-symptoms-all'],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get<{ symptoms: SymptomItem[] }>('/nlp/symptoms');
        return data.symptoms;
      } catch {
        return DEMO_ALL_SYMPTOMS;
      }
    },
    staleTime: 10 * 60 * 1000,
    initialData: DEMO_ALL_SYMPTOMS,
  });

  // ── Search query ──────────────────────────────────────────────────────────
  const { data: searchResults, isLoading: searchLoading } = useQuery<SearchResult[]>({
    queryKey: ['nlp-symptom-search', debouncedQ],
    queryFn: async () => {
      if (!debouncedQ) return [];
      try {
        const { data } = await apiClient.get<{ results: SearchResult[] }>(
          '/nlp/symptoms/search',
          { params: { q: debouncedQ } },
        );
        return data.results;
      } catch {
        return demoSearch(debouncedQ);
      }
    },
    enabled: debouncedQ.length > 0,
    staleTime: 30_000,
  });

  // ── Extract mutation ──────────────────────────────────────────────────────
  const extractMutation = useMutation({
    mutationFn: async (text: string) => {
      try {
        const { data } = await apiClient.post<ExtractResult>('/nlp/extract', { text });
        return data;
      } catch {
        await new Promise((r) => setTimeout(r, 900));
        return DEMO_EXTRACT;
      }
    },
    onSuccess: (result) => {
      setExtractResult(result);
      Keyboard.dismiss();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    },
  });

  const toggleSymptom = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
    Haptics.selectionAsync();
  }, []);

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
        <Text style={s.headerTitle}>Symptom Explorer</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

        {/* Selected symptoms */}
        {selected.size > 0 && (
          <Animated.View entering={FadeInDown.duration(300)}>
            <Text style={s.sectionLabel}>SELECTED ({selected.size})</Text>
            <View style={s.chipWrap}>
              {(allSymptoms ?? [])
                .filter((sym) => selected.has(sym.id))
                .map((sym) => (
                  <Chip
                    key={sym.id}
                    label={`${sym.name} ✕`}
                    selected
                    onPress={() => toggleSymptom(sym.id)}
                  />
                ))}
            </View>
          </Animated.View>
        )}

        {/* Search bar */}
        <Animated.View entering={FadeInDown.duration(400)}>
          <View style={s.searchBar}>
            <Text style={s.searchIcon}>🔍</Text>
            <TextInput
              style={s.searchInput}
              value={searchQ}
              onChangeText={setSearchQ}
              placeholder="Search symptoms…"
              placeholderTextColor={COLORS.textFaint}
              returnKeyType="search"
              autoCorrect={false}
            />
            {searchQ.length > 0 && (
              <TouchableOpacity onPress={() => { setSearchQ(''); setDebouncedQ(''); }}>
                <Text style={s.clearText}>✕</Text>
              </TouchableOpacity>
            )}
          </View>
        </Animated.View>

        {/* Search results */}
        {debouncedQ.length > 0 && (
          <Animated.View entering={FadeInDown.duration(300)}>
            <View style={s.card}>
              {searchLoading && (
                <ActivityIndicator color={COLORS.sage} style={{ paddingVertical: 12 }} />
              )}
              {!searchLoading && (searchResults ?? []).length === 0 && (
                <Text style={s.emptyText}>No matches for "{debouncedQ}"</Text>
              )}
              {(searchResults ?? []).map((r, i) => {
                const isLast = i === (searchResults ?? []).length - 1;
                return (
                  <TouchableOpacity
                    key={r.symptom.id}
                    style={[s.resultRow, !isLast && s.resultRowBorder]}
                    onPress={() => toggleSymptom(r.symptom.id)}
                    activeOpacity={0.7}
                  >
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text style={s.resultName}>{r.symptom.name}</Text>
                      <ScoreBar score={r.score} />
                    </View>
                    <View style={[chip.base, selected.has(r.symptom.id) && chip.selected, { marginLeft: 8 }]}>
                      <Text style={[chip.text, selected.has(r.symptom.id) && chip.textSelected]}>
                        {selected.has(r.symptom.id) ? 'Added' : 'Add'}
                      </Text>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          </Animated.View>
        )}

        {/* Extract from text */}
        <Animated.View entering={FadeInDown.duration(400).delay(80)}>
          <Text style={s.sectionLabel}>EXTRACT FROM TEXT</Text>
          <View style={s.card}>
            <TextInput
              style={s.multilineInput}
              value={extractText}
              onChangeText={setExtractText}
              placeholder="Type or paste a description of symptoms…"
              placeholderTextColor={COLORS.textFaint}
              multiline
              numberOfLines={4}
              textAlignVertical="top"
            />
            <TouchableOpacity
              style={[s.analyseBtn, (extractMutation.isPending || extractText.length < 5) && s.analyseBtnDim]}
              onPress={() => extractMutation.mutate(extractText)}
              disabled={extractMutation.isPending || extractText.length < 5}
              activeOpacity={0.85}
            >
              {extractMutation.isPending
                ? <ActivityIndicator color={COLORS.parchment} size="small" />
                : <Text style={s.analyseBtnText}>Analyse</Text>
              }
            </TouchableOpacity>

            {extractResult && !extractMutation.isPending && (
              <Animated.View entering={FadeInDown.duration(300)} style={s.extractResult}>
                {/* Extracted symptom chips */}
                <Text style={s.extractLabel}>Extracted symptoms</Text>
                <View style={s.chipWrap}>
                  {extractResult.symptoms.map((sym) => (
                    <Chip
                      key={sym.id}
                      label={sym.name}
                      selected={selected.has(sym.id)}
                      onPress={() => toggleSymptom(sym.id)}
                      small
                    />
                  ))}
                </View>

                {/* Duration */}
                {extractResult.duration && (
                  <View style={s.extractRow}>
                    <Text style={s.extractKey}>Duration</Text>
                    <Text style={s.extractVal}>{extractResult.duration}</Text>
                  </View>
                )}

                {/* Severity */}
                <View style={s.extractRow}>
                  <Text style={s.extractKey}>Severity estimate</Text>
                  <SeverityBar value={extractResult.severity_estimate} />
                </View>

                {/* Body parts */}
                {extractResult.body_parts.length > 0 && (
                  <View style={s.extractRow}>
                    <Text style={s.extractKey}>Body parts</Text>
                    <Text style={s.extractVal}>{extractResult.body_parts.join(', ')}</Text>
                  </View>
                )}
              </Animated.View>
            )}
          </View>
        </Animated.View>

        {/* All symptoms */}
        <Animated.View entering={FadeInDown.duration(400).delay(160)}>
          <Text style={s.sectionLabel}>ALL SYMPTOMS</Text>
          <View style={s.chipWrap}>
            {(allSymptoms ?? DEMO_ALL_SYMPTOMS).map((sym) => (
              <Chip
                key={sym.id}
                label={sym.name}
                selected={selected.has(sym.id)}
                onPress={() => toggleSymptom(sym.id)}
                small
              />
            ))}
          </View>
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

  scroll: { padding: 20, paddingBottom: 52, gap: 16 },

  sectionLabel: { ...TYPE.micro, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8, paddingHorizontal: 2, fontWeight: '700' },

  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 4 },

  searchBar:   { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.surface, borderRadius: RADIUS.xl, borderWidth: 1.5, borderColor: COLORS.border, paddingHorizontal: 14, height: 52, gap: 8 },
  searchIcon:  { fontSize: 15 },
  searchInput: { flex: 1, ...TYPE.bodyMed, color: COLORS.ink },
  clearText:   { fontSize: 14, color: COLORS.textFaint, padding: 4 },

  card: {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 14,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05, shadowRadius: 6, elevation: 2,
  },

  resultRow:       { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 10 },
  resultRowBorder: { borderBottomWidth: 1, borderBottomColor: COLORS.border },
  resultName:      { ...TYPE.titleMed, color: COLORS.ink },

  emptyText: { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center', paddingVertical: 12 },

  multilineInput: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.lg,
    padding: 12, ...TYPE.bodyMed, color: COLORS.ink,
    minHeight: 100, marginBottom: 12, backgroundColor: COLORS.parchment,
  },
  analyseBtn:    { backgroundColor: COLORS.sage, borderRadius: RADIUS.lg, paddingVertical: 13, alignItems: 'center' },
  analyseBtnDim: { opacity: 0.45 },
  analyseBtnText:{ ...TYPE.titleLarge, color: COLORS.surface },

  extractResult: { marginTop: 14, gap: 12, borderTopWidth: 1, borderTopColor: COLORS.border, paddingTop: 14 },
  extractLabel:  { ...TYPE.micro, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 0.8, fontWeight: '700' },
  extractRow:    { flexDirection: 'row', alignItems: 'center', gap: 10 },
  extractKey:    { ...TYPE.micro, color: COLORS.textMuted, fontWeight: '600', width: 110 },
  extractVal:    { ...TYPE.bodySmall, color: COLORS.ink, flex: 1 },
});
