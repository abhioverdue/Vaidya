/**
 * Vaidya — Symptom Input screen  (v3 · Senior Apple Designer Redesign)
 * Voice waveform visualizer, image preview, spring chip animations, elevated mic button.
 */

import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, Alert, Pressable, Image,
} from 'react-native';
import { useState, useRef, useCallback, useEffect } from 'react';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import Animated, {
  FadeInDown, FadeIn,
  useAnimatedStyle, useSharedValue,
  withRepeat, withTiming, withSequence, withSpring, withDelay,
  interpolate, Easing,
} from 'react-native-reanimated';
import * as ImagePicker from 'expo-image-picker';
import { Audio } from 'expo-av';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { useTriage } from '@/hooks/useTriage';
import { submitVoice } from '@/services/api';
import { COLORS, QUICK_SYMPTOMS, TYPE, RADIUS } from '@/constants';
import { OfflineBanner } from '@/components/ui/OfflineBanner';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { PillBadge } from '@/components/ui/PillBadge';
import type { Language } from '@/types';

const DURATIONS = ['Today', '2–3 days', '1 week', 'Longer'] as const;
type DurationLabel = typeof DURATIONS[number];

// ── RecordingWaveBar ──────────────────────────────────────────────────────────

function RecordingWaveBar({ isActive, index }: { isActive: boolean; index: number }) {
  const height = useSharedValue(4);

  useEffect(() => {
    if (isActive) {
      const randomH = 12 + Math.random() * 28;
      height.value = withDelay(
        index * 40,
        withRepeat(
          withSequence(
            withTiming(randomH, { duration: 250 + (index % 5) * 60, easing: Easing.inOut(Easing.sin) }),
            withTiming(4 + Math.random() * 8, { duration: 250 + (index % 4) * 60, easing: Easing.inOut(Easing.sin) }),
          ),
          -1,
          false,
        ),
      );
    } else {
      height.value = withSpring(4, { damping: 15, stiffness: 200 });
    }
  }, [isActive]);

  const style = useAnimatedStyle(() => ({ height: height.value }));

  return (
    <Animated.View
      style={[
        {
          width: 3,
          borderRadius: 2,
          backgroundColor: isActive ? COLORS.crimson : COLORS.border,
        },
        style,
      ]}
    />
  );
}

// ── WaveformVisualizer ────────────────────────────────────────────────────────

const BAR_COUNT = 28;

function WaveformVisualizer({ isRecording }: { isRecording: boolean }) {
  return (
    <View style={wv.row}>
      {Array.from({ length: BAR_COUNT }, (_, i) => (
        <RecordingWaveBar key={i} isActive={isRecording} index={i} />
      ))}
    </View>
  );
}

const wv = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    height: 44,
    paddingHorizontal: 4,
  },
});

// ── SymptomChip ───────────────────────────────────────────────────────────────

function SymptomChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  const scale = useSharedValue(1);

  const handlePress = useCallback(async () => {
    scale.value = withSequence(
      withSpring(0.88, { damping: 18, stiffness: 400 }),
      withSpring(1,    { damping: 14, stiffness: 300 }),
    );
    await Haptics.selectionAsync();
    onPress();
  }, [onPress]);

  const animStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  return (
    <Animated.View style={animStyle}>
      <Pressable
        style={[s.chip, active && s.chipActive]}
        onPress={handlePress}
      >
        {active && <View style={s.chipDot} />}
        <Text style={[s.chipText, active && s.chipTextActive]}>{label}</Text>
      </Pressable>
    </Animated.View>
  );
}

// ── ImagePreviewCard ──────────────────────────────────────────────────────────

function ImagePreviewCard({ uri, task, onRemove }: { uri: string; task?: string; onRemove: () => void }) {
  return (
    <Animated.View entering={FadeInDown.duration(300)} style={s.imagePreviewCard}>
      <Image source={{ uri }} style={s.imageThumb} resizeMode="cover" />
      <View style={s.imagePreviewInfo}>
        <Text style={s.imagePreviewTitle}>Image attached</Text>
        {task && (
          <Text style={s.imagePreviewSub}>
            {task === 'chest' ? 'Chest X-ray' : task === 'skin' ? 'Skin condition' : 'Wound / injury'}
          </Text>
        )}
      </View>
      <TouchableOpacity onPress={onRemove} style={s.imageRemoveBtn}>
        <Text style={s.imageRemoveText}>×</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

// ── SymptomScreen ─────────────────────────────────────────────────────────────

export default function SymptomScreen() {
  const { t }         = useTranslation();
  const store         = useAppStore();
  const { runTriage } = useTriage();

  const [isRecording, setIsRecording]         = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [selectedChips, setSelectedChips]     = useState<string[]>([]);
  const [showAdvanced, setShowAdvanced]       = useState(false);
  const [showImageTaskModal, setShowImageTaskModal] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);

  const lang  = store.language as Language;
  const chips = QUICK_SYMPTOMS[lang];
  const canSubmit = !!(store.symptomText.trim() || selectedChips.length > 0);

  // Submit button pulse when ready
  const submitGlow = useSharedValue(0);
  useEffect(() => {
    if (canSubmit) {
      submitGlow.value = withRepeat(
        withSequence(
          withTiming(1, { duration: 1200, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: 1200, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
        false,
      );
    } else {
      submitGlow.value = withTiming(0);
    }
  }, [canSubmit]);

  const submitScale = useSharedValue(1);
  const submitAnimStyle = useAnimatedStyle(() => ({
    transform: [{ scale: submitScale.value }],
    shadowOpacity: interpolate(submitGlow.value, [0, 1], [0.08, 0.24]),
  }));

  // ── Chip helpers ────────────────────────────────────────────────────────────

  const toggleChip = useCallback((chip: string) => {
    setSelectedChips((prev) => {
      const next = prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip];
      store.setSymptomText(next.join(', '));
      return next;
    });
  }, [store]);

  const removeChip = useCallback((chip: string) => {
    setSelectedChips((prev) => {
      const next = prev.filter((c) => c !== chip);
      store.setSymptomText(next.join(', '));
      return next;
    });
  }, [store]);

  // ── Voice recording ─────────────────────────────────────────────────────────

  async function startRecording() {
    try {
      const { granted } = await Audio.requestPermissionsAsync();
      if (!granted) {
        Alert.alert(t('voice.permission_title'), t('voice.permission_body'));
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recordingRef.current = recording;
      setIsRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch {
      Alert.alert(t('errors.microphone'));
    }
  }

  async function stopRecording() {
    if (!recordingRef.current) return;
    setIsRecording(false);
    await recordingRef.current.stopAndUnloadAsync();
    const uri = recordingRef.current.getURI();
    recordingRef.current = null;
    if (!uri) return;
    store.setAudioUri(uri);
    if (store.isOnline) {
      try {
        const result = await submitVoice(uri, lang);
        const { transcript } = result;
        setVoiceTranscript(transcript);
        store.setSymptomText(store.symptomText ? `${store.symptomText}. ${transcript}` : transcript);
      } catch { /* silent — user still has text input */ }
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }

  async function pickImage() {
    const { granted } = await ImagePicker.requestCameraPermissionsAsync();
    if (!granted) return;
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8, base64: false });
    if (!result.canceled && result.assets[0]) {
      store.setImageUri(result.assets[0].uri);
      setShowImageTaskModal(true);
    }
  }

  function handleSubmit() {
    const text = store.symptomText.trim();
    if (!text) return;
    runTriage(text);
  }

  const severityColor = (n: number) => {
    if (n <= 3) return COLORS.t1;
    if (n <= 5) return COLORS.t2;
    if (n <= 7) return COLORS.t3;
    if (n <= 9) return COLORS.t4;
    return COLORS.t5;
  };

  return (
    <SafeAreaView style={s.safe}>

      {/* ── Header ────────────────────────────────────────────────────── */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} accessibilityLabel="Go back">
          <View style={s.backCircle}>
            <Text style={s.backGlyph}>←</Text>
          </View>
        </TouchableOpacity>
        <View style={s.headerCenter}>
          <Text style={s.headerTitle}>Symptom Check</Text>
          <StatusIndicator online={store.isOnline} />
        </View>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {!store.isOnline && <OfflineBanner />}

        {/* ── Voice section ──────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(380)} style={s.voiceCard}>
          {/* Mode label */}
          <View style={s.voiceCardTop}>
            <Text style={s.sectionLabel}>VOICE INPUT</Text>
            {store.audioUri && (
              <PillBadge label="Audio ready" color={COLORS.sage} bg={COLORS.sageGhost} size="sm" />
            )}
          </View>

          {/* Big mic button */}
          <View style={s.micCenter}>
            <TouchableOpacity
              onPress={isRecording ? stopRecording : startRecording}
              activeOpacity={0.85}
            >
              <View style={[s.micOuter, isRecording && s.micOuterActive]}>
                <View style={[s.micBtn, isRecording && s.micBtnActive]}>
                  {isRecording
                    ? <View style={s.stopIcon} />
                    : <View style={s.micIcon}>
                        <View style={s.micIconBody} />
                        <View style={s.micIconStand} />
                        <View style={s.micIconBase} />
                      </View>
                  }
                </View>
              </View>
            </TouchableOpacity>

            <View style={s.micMeta}>
              <Text style={isRecording ? s.recordingLabel : s.voiceHint}>
                {isRecording ? 'Recording — tap to stop' : 'Tap to record'}
              </Text>
              <Text style={s.voiceSubHint}>
                {isRecording ? `Listening in ${lang.toUpperCase()}…` : 'English · Hindi · Tamil'}
              </Text>
            </View>
          </View>

          {/* Waveform */}
          <WaveformVisualizer isRecording={isRecording} />

          {/* Transcript */}
          {voiceTranscript ? (
            <Animated.View entering={FadeIn.duration(300)} style={s.transcriptWrap}>
              <Text style={s.transcriptLabel}>TRANSCRIPT</Text>
              <Text style={s.transcript}>{voiceTranscript}</Text>
            </Animated.View>
          ) : null}
        </Animated.View>

        {/* ── Text input ─────────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(380).delay(55)} style={s.textCard}>
          <View style={s.textCardTop}>
            <Text style={s.sectionLabel}>DESCRIBE IN WORDS</Text>
            <TouchableOpacity onPress={pickImage} style={s.cameraChip}>
              <Text style={s.cameraChipText}>
                {store.imageUri ? '✓ Photo' : '+ Photo'}
              </Text>
            </TouchableOpacity>
          </View>

          <TextInput
            style={s.textInput}
            placeholder="e.g. Fever and headache for two days, feeling weak..."
            placeholderTextColor={COLORS.textFaint}
            value={store.symptomText}
            onChangeText={store.setSymptomText}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
          />

          {store.symptomText.length > 0 && (
            <TouchableOpacity onPress={() => store.setSymptomText('')} style={s.clearRow}>
              <Text style={s.clearBtn}>Clear text</Text>
            </TouchableOpacity>
          )}
        </Animated.View>

        {/* ── Image preview ──────────────────────────────────────────── */}
        {store.imageUri && (
          <ImagePreviewCard
            uri={store.imageUri}
            task={store.imageTask ?? undefined}
            onRemove={() => store.setImageUri(null)}
          />
        )}

        {/* ── Common symptom chips ───────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(380).delay(110)}>
          <SectionHeader
            title="Common symptoms"
            badge={selectedChips.length > 0 ? selectedChips.length : undefined}
          />
          <View style={s.chips}>
            {chips.map((chip, i) => (
              <SymptomChip
                key={chip}
                label={chip}
                active={selectedChips.includes(chip)}
                onPress={() => toggleChip(chip)}
              />
            ))}
          </View>
        </Animated.View>

        {/* ── Selected pills ─────────────────────────────────────────── */}
        {selectedChips.length > 0 && (
          <Animated.View entering={FadeIn.duration(220)} style={s.selectedWrap}>
            <Text style={s.selectedLabel}>{selectedChips.length} selected</Text>
            <View style={s.selectedPills}>
              {selectedChips.map((chip) => (
                <TouchableOpacity key={chip} onPress={() => removeChip(chip)} style={s.selectedPill}>
                  <Text style={s.selectedPillText}>{chip} ×</Text>
                </TouchableOpacity>
              ))}
            </View>
          </Animated.View>
        )}

        {/* ── Advanced: duration + severity ─────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(380).delay(165)}>
          <TouchableOpacity
            style={s.advancedToggle}
            onPress={() => { setShowAdvanced((v) => !v); Haptics.selectionAsync(); }}
          >
            <Text style={s.advancedToggleText}>
              {showAdvanced ? 'Hide' : 'Add'} duration & severity
            </Text>
            <View style={[s.chevronWrap, showAdvanced && s.chevronWrapOpen]}>
              <Text style={s.advancedChevron}>›</Text>
            </View>
          </TouchableOpacity>

          {showAdvanced && (
            <Animated.View entering={FadeInDown.duration(240)} style={s.advancedCard}>
              {/* Duration */}
              <Text style={s.subLabel}>Duration</Text>
              <View style={s.durationRow}>
                {DURATIONS.map((d) => {
                  const active = store.duration === d;
                  return (
                    <TouchableOpacity
                      key={d}
                      style={[s.durationBtn, active && s.durationBtnActive]}
                      onPress={() => { store.setDuration(d); Haptics.selectionAsync(); }}
                    >
                      <Text style={[s.durationText, active && s.durationTextActive]}>{d}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Severity */}
              <View style={s.severityHeader}>
                <Text style={s.subLabel}>Severity</Text>
                <PillBadge
                  label={`${store.severity} / 10`}
                  color={severityColor(store.severity)}
                  bg="transparent"
                  size="sm"
                />
              </View>
              <View style={s.severityRow}>
                {([1,2,3,4,5,6,7,8,9,10] as const).map((n) => {
                  const active = store.severity === n;
                  return (
                    <TouchableOpacity
                      key={n}
                      style={[s.sevBtn, active && { backgroundColor: severityColor(n), borderColor: severityColor(n) }]}
                      onPress={() => { store.setSeverity(n); Haptics.selectionAsync(); }}
                    >
                      <Text style={[s.sevText, active && s.sevTextActive]}>{n}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </Animated.View>
          )}
        </Animated.View>

        <View style={{ height: 130 }} />
      </ScrollView>

      {/* ── Floating submit dock ──────────────────────────────────────── */}
      <View style={s.submitDock}>
        <Animated.View style={[s.submitBtnWrap, submitAnimStyle]}>
          <Pressable
            style={[s.submitBtn, !canSubmit && s.submitBtnDisabled]}
            onPress={handleSubmit}
            onPressIn={() => { submitScale.value = withSpring(0.97, { damping: 20, stiffness: 300 }); }}
            onPressOut={() => { submitScale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }}
            disabled={!canSubmit}
          >
            <Text style={s.submitText}>
              {store.isAnalysing ? 'Analysing…' : 'Analyse symptoms →'}
            </Text>
          </Pressable>
        </Animated.View>
        <Text style={s.submitHint}>
          {store.isOnline ? 'Gemini AI + XGBoost · 132 conditions' : 'On-device TFLite · offline model'}
        </Text>
      </View>

      {/* ── Image task modal ──────────────────────────────────────────── */}
      {showImageTaskModal && (
        <View style={s.modalOverlay}>
          <Animated.View entering={FadeInDown.duration(340)} style={s.modalContent}>
            <View style={s.modalHandle} />
            <Text style={s.modalTitle}>What type of image?</Text>
            <Text style={s.modalSub}>This helps our AI analyse it more accurately</Text>
            <View style={s.modalOptions}>
              {[
                { key: 'chest', label: 'Chest X-ray',      icon: '🫁', hint: 'Respiratory analysis' },
                { key: 'skin',  label: 'Skin condition',   icon: '🩹', hint: 'Dermatology scan' },
                { key: 'wound', label: 'Wound or injury',  icon: '🩸', hint: 'Wound assessment' },
              ].map(({ key, label, icon, hint }) => (
                <TouchableOpacity
                  key={key}
                  style={s.modalOption}
                  onPress={() => {
                    store.setImageTask(key as 'chest' | 'skin' | 'wound');
                    setShowImageTaskModal(false);
                    Haptics.selectionAsync();
                  }}
                >
                  <Text style={s.modalOptionIcon}>{icon}</Text>
                  <View style={s.modalOptionText}>
                    <Text style={s.modalOptionLabel}>{label}</Text>
                    <Text style={s.modalOptionHint}>{hint}</Text>
                  </View>
                  <Text style={s.modalOptionArrow}>›</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity
              style={s.modalCancel}
              onPress={() => {
                store.setImageUri(null);
                setShowImageTaskModal(false);
              }}
            >
              <Text style={s.modalCancelText}>Cancel</Text>
            </TouchableOpacity>
          </Animated.View>
        </View>
      )}
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: COLORS.parchment },

  // Header
  header:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  backBtn:      { width: 40, height: 40, justifyContent: 'center' },
  backCircle:   { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.parchmentWarm, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backGlyph:    { fontSize: 17, color: COLORS.ink, marginTop: -1 },
  headerCenter: { alignItems: 'center', gap: 5 },
  headerTitle:  { ...TYPE.titleLarge, color: COLORS.ink },

  scroll:        { flex: 1 },
  scrollContent: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120, gap: 12 },

  sectionLabel: { ...TYPE.micro, color: COLORS.textMuted, letterSpacing: 1.4, fontWeight: '700' },
  subLabel:     { ...TYPE.bodySmall, color: COLORS.textSub, fontWeight: '600', marginBottom: 10 },

  // Voice card
  voiceCard:    {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl,
    padding: 18,
    borderWidth: 1,
    borderColor: COLORS.border,
    shadowColor: COLORS.ink,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
    gap: 14,
  },
  voiceCardTop:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },

  micCenter:      { alignItems: 'center', gap: 12 },
  micOuter:       {
    width: 92, height: 92, borderRadius: 46,
    borderWidth: 1.5, borderColor: COLORS.borderMid,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: COLORS.parchmentWarm,
  },
  micOuterActive: { borderColor: COLORS.crimson, backgroundColor: 'rgba(194,59,34,0.06)' },
  micBtn:         {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: COLORS.parchment,
    borderWidth: 1, borderColor: COLORS.border,
    alignItems: 'center', justifyContent: 'center',
  },
  micBtnActive:   { backgroundColor: COLORS.crimson, borderColor: COLORS.crimson },

  // Mic icon (custom SVG-less icon)
  micIcon:      { alignItems: 'center', gap: 2 },
  micIconBody:  { width: 14, height: 20, borderRadius: 7, backgroundColor: COLORS.inkSoft, borderWidth: 1.5, borderColor: COLORS.inkMid },
  micIconStand: { width: 18, height: 8, borderTopLeftRadius: 0, borderTopRightRadius: 0, borderBottomLeftRadius: 10, borderBottomRightRadius: 10, borderWidth: 1.5, borderTopWidth: 0, borderColor: COLORS.inkSoft },
  micIconBase:  { width: 2, height: 4, backgroundColor: COLORS.inkSoft, borderRadius: 1 },

  stopIcon:   { width: 16, height: 16, borderRadius: 3, backgroundColor: '#fff' },

  micMeta:        { alignItems: 'center', gap: 3 },
  recordingLabel: { ...TYPE.titleMed, color: COLORS.crimson },
  voiceHint:      { ...TYPE.titleMed, color: COLORS.textSub },
  voiceSubHint:   { ...TYPE.micro, color: COLORS.textFaint },

  transcriptWrap:  { backgroundColor: COLORS.parchment, borderRadius: RADIUS.md, padding: 12, borderWidth: 1, borderColor: COLORS.border },
  transcriptLabel: { ...TYPE.micro, color: COLORS.sage, fontWeight: '700', letterSpacing: 1, marginBottom: 4 },
  transcript:      { ...TYPE.bodySmall, color: COLORS.textSub, fontStyle: 'italic', lineHeight: 20 },

  // Text card
  textCard:    {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl,
    padding: 18,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 12,
  },
  textCardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },

  textInput: {
    ...TYPE.bodyMed,
    color: COLORS.ink,
    minHeight: 96,
    borderWidth: 1, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 14,
    backgroundColor: COLORS.parchment,
  },
  clearRow: { alignItems: 'flex-end' },
  clearBtn: { ...TYPE.bodySmall, color: COLORS.textMuted },

  cameraChip:     { backgroundColor: COLORS.sageGhost, borderRadius: RADIUS.pill, paddingHorizontal: 12, paddingVertical: 5, borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)' },
  cameraChipText: { ...TYPE.micro, color: COLORS.sage, fontWeight: '700' },

  // Image preview
  imagePreviewCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  imageThumb:        { width: 56, height: 56, borderRadius: RADIUS.md, backgroundColor: COLORS.parchmentWarm },
  imagePreviewInfo:  { flex: 1, gap: 3 },
  imagePreviewTitle: { ...TYPE.titleMed, color: COLORS.ink },
  imagePreviewSub:   { ...TYPE.micro, color: COLORS.textMuted },
  imageRemoveBtn:    { width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.inkGhost, alignItems: 'center', justifyContent: 'center' },
  imageRemoveText:   { fontSize: 18, color: COLORS.textMuted, fontWeight: '400', lineHeight: 20 },

  // Chips
  chips:          { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 4 },
  chip:           {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 14, paddingVertical: 9,
    borderRadius: RADIUS.pill,
    backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
  },
  chipActive:     { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  chipDot:        { width: 5, height: 5, borderRadius: 3, backgroundColor: COLORS.sage },
  chipText:       { ...TYPE.bodySmall, color: COLORS.textSub, fontWeight: '500' },
  chipTextActive: { color: '#fff', fontWeight: '600' },

  // Selected pills summary
  selectedWrap:    { backgroundColor: COLORS.inkGhost, borderRadius: RADIUS.md, padding: 12, borderWidth: 1, borderColor: COLORS.borderMid },
  selectedLabel:   { ...TYPE.label, color: COLORS.textMuted, letterSpacing: 1, marginBottom: 8 },
  selectedPills:   { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  selectedPill:    { backgroundColor: COLORS.ink, borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 5 },
  selectedPillText:{ ...TYPE.micro, color: '#fff', fontWeight: '600' },

  // Advanced section
  advancedToggle:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12 },
  advancedToggleText: { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '600' },
  chevronWrap:        { width: 24, height: 24, borderRadius: 12, backgroundColor: COLORS.parchmentWarm, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  chevronWrapOpen:    { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  advancedChevron:    { fontSize: 16, color: COLORS.textFaint, fontWeight: '400', marginTop: -1 },

  advancedCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl,
    padding: 18,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 8,
  },

  durationRow:        { flexDirection: 'row', gap: 6, marginBottom: 16 },
  durationBtn:        { flex: 1, paddingVertical: 10, borderRadius: RADIUS.sm, backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center' },
  durationBtnActive:  { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  durationText:       { ...TYPE.bodySmall, color: COLORS.textSub, fontWeight: '500' },
  durationTextActive: { color: '#fff', fontWeight: '600' },

  severityHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 0 },
  severityRow:    { flexDirection: 'row', gap: 4 },
  sevBtn:         { flex: 1, paddingVertical: 10, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', backgroundColor: COLORS.parchment },
  sevText:        { fontSize: 11, fontWeight: '600', color: COLORS.textMuted },
  sevTextActive:  { color: '#fff' },

  // Submit dock
  submitDock: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: COLORS.parchment,
    paddingHorizontal: 20, paddingTop: 14, paddingBottom: 30,
    borderTopWidth: 1, borderTopColor: COLORS.border,
  },
  submitBtnWrap: {
    shadowColor: COLORS.ink,
    shadowOffset: { width: 0, height: 6 },
    shadowRadius: 16,
    elevation: 8,
    borderRadius: RADIUS.xl,
  },
  submitBtn:         { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 20, alignItems: 'center' },
  submitBtnDisabled: { backgroundColor: COLORS.borderMid },
  submitText:        { ...TYPE.titleLarge, color: COLORS.textInverse, letterSpacing: 0.2, fontSize: 17 },
  submitHint:        { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', marginTop: 8, letterSpacing: 0.2 },

  // Modal
  modalOverlay:     { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15,17,23,0.55)', justifyContent: 'flex-end' },
  modalContent:     { backgroundColor: COLORS.parchment, borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 28, paddingBottom: 40, gap: 8 },
  modalHandle:      { width: 36, height: 4, borderRadius: 2, backgroundColor: COLORS.borderMid, alignSelf: 'center', marginBottom: 8 },
  modalTitle:       { ...TYPE.headlineMed, color: COLORS.ink, textAlign: 'center' },
  modalSub:         { ...TYPE.bodySmall, color: COLORS.textMuted, textAlign: 'center', marginBottom: 8 },
  modalOptions:     { gap: 10, marginTop: 4 },
  modalOption:      { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: RADIUS.lg, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, gap: 14 },
  modalOptionIcon:  { fontSize: 24 },
  modalOptionText:  { flex: 1, gap: 2 },
  modalOptionLabel: { ...TYPE.titleMed, color: COLORS.ink },
  modalOptionHint:  { ...TYPE.micro, color: COLORS.textMuted },
  modalOptionArrow: { fontSize: 20, color: COLORS.textFaint, fontWeight: '300' },
  modalCancel:      { marginTop: 8, paddingVertical: 14, alignItems: 'center' },
  modalCancelText:  { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '600' },
});
