/**
 * Vaidya — Result screen  (v3 · Senior Apple Designer Redesign)
 * Animated confidence bars, full-bleed triage banner, spring action buttons.
 */

import {
  View, Text, TouchableOpacity, ScrollView,
  StyleSheet, Linking, Share, Pressable,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import Animated, {
  FadeInDown, FadeInUp,
  useSharedValue, useAnimatedStyle,
  withSpring, withTiming, withDelay,
  Easing,
} from 'react-native-reanimated';
import { useCallback, useEffect, useState } from 'react';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { COLORS, TRIAGE_CONFIG, TYPE, RADIUS } from '@/constants';
import { mScale, scale } from '@/utils/responsive';
import { TriageTag } from '@/components/ui/TriageTag';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GradientCard } from '@/components/ui/GradientCard';
import { PillBadge } from '@/components/ui/PillBadge';
import type { DiagnosisResult, FullTriageResponse, OfflinePrediction, TriageLevel } from '@/types';

// ── Type guards ───────────────────────────────────────────────────────────────

function isFullTriage(r: unknown): r is FullTriageResponse {
  return !!r && typeof r === 'object' && 'triage' in r && 'diagnosis' in r;
}

// ── AnimatedConfidenceBar ─────────────────────────────────────────────────────

function AnimatedConfidenceBar({ value, color, delay = 0 }: { value: number; color: string; delay?: number }) {
  const width = useSharedValue(0);

  useEffect(() => {
    width.value = withDelay(
      delay,
      withTiming(value, { duration: 800, easing: Easing.out(Easing.cubic) }),
    );
  }, [value, delay]);

  const barStyle = useAnimatedStyle(() => ({
    width: `${width.value}%` as any,
  }));

  return (
    <View style={acb.row}>
      <View style={acb.track}>
        <Animated.View style={[acb.fill, { backgroundColor: color }, barStyle]} />
      </View>
      <Text style={[acb.pct, { color }]}>{value}%</Text>
    </View>
  );
}

const acb = StyleSheet.create({
  row:   { flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 },
  track: { flex: 1, height: 5, backgroundColor: COLORS.border, borderRadius: 3, overflow: 'hidden' },
  fill:  { height: '100%', borderRadius: 3 },
  pct:   { ...TYPE.titleMed, fontSize: 13, width: 38, textAlign: 'right', fontWeight: '700' },
});

// ── ActionButton ──────────────────────────────────────────────────────────────

function ActionButton({
  label, onPress, variant = 'secondary', fullWidth = false,
}: { label: string; onPress: () => void; variant?: 'primary' | 'secondary' | 'danger' | 'outline'; fullWidth?: boolean }) {
  const scale = useSharedValue(1);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const onPressIn  = useCallback(() => { scale.value = withSpring(0.96, { damping: 20, stiffness: 300 }); }, []);
  const onPressOut = useCallback(() => { scale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }, []);

  const bg =
    variant === 'primary'   ? COLORS.ink :
    variant === 'danger'    ? COLORS.crimson :
    variant === 'outline'   ? 'transparent' :
    COLORS.surface;

  const borderColor =
    variant === 'secondary' ? COLORS.border :
    variant === 'outline'   ? COLORS.borderMid :
    'transparent';

  const textColor =
    variant === 'secondary' ? COLORS.ink :
    variant === 'outline'   ? COLORS.textSub :
    '#fff';

  return (
    <Animated.View style={[aStyle, fullWidth ? { width: '100%' } : { flex: 1 }]}>
      <Pressable
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        onPress={async () => { await Haptics.selectionAsync(); onPress(); }}
        style={[s.actionBtn, { backgroundColor: bg, borderColor, borderWidth: 1 }]}
      >
        <Text style={[s.actionBtnText, { color: textColor }]}>{label}</Text>
      </Pressable>
    </Animated.View>
  );
}

// ── ScoreRing ─────────────────────────────────────────────────────────────────

function ScoreRing({ confidence, color }: { confidence: number; color: string }) {
  const size = 72;
  const strokeW = 5;
  const r = (size - strokeW * 2) / 2;
  const circum = 2 * Math.PI * r;
  const dashOffset = useSharedValue(circum);
  const targetOffset = circum * (1 - confidence / 100);

  useEffect(() => {
    dashOffset.value = withDelay(
      200,
      withTiming(targetOffset, { duration: 1000, easing: Easing.out(Easing.cubic) }),
    );
  }, [confidence]);

  // Use a simple View-based ring as SVG may have issues with animated stroke
  const filled = useSharedValue(0);
  useEffect(() => {
    filled.value = withDelay(200, withTiming(confidence, { duration: 1000, easing: Easing.out(Easing.cubic) }));
  }, [confidence]);

  const arcStyle = useAnimatedStyle(() => ({
    width: size,
    height: size / 2,
    borderTopLeftRadius: size / 2,
    borderTopRightRadius: size / 2,
    backgroundColor: filled.value > 50 ? color : COLORS.border,
    overflow: 'hidden',
  }));

  return (
    <View style={[sr.ring, { width: size, height: size, borderRadius: size / 2, borderColor: color }]}>
      <Text style={[sr.pct, { color }]}>{confidence}</Text>
      <Text style={sr.label}>%</Text>
    </View>
  );
}

const sr = StyleSheet.create({
  ring:  { borderWidth: 5, alignItems: 'center', justifyContent: 'center', gap: 0 },
  pct:   { fontSize: 18, fontWeight: '800', letterSpacing: -0.5 },
  label: { ...TYPE.micro, color: COLORS.textFaint, marginTop: -2 },
});

// ── SOURCE LABELS ─────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  xgboost:        'AI symptom analysis',
  fusion:         'Multimodal AI analysis',
  llm_fallback:   'Gemini AI analysis',
  llm_gemini:     'Gemini AI analysis',
  tflite_offline: 'On-device AI · offline',
};

// ── ResultScreen ──────────────────────────────────────────────────────────────

export default function ResultScreen() {
  const { t }   = useTranslation();
  const session = useAppStore((s) => s.currentSession);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  if (!session) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.center}>
          <Text style={s.errorText}>{t('common.error')}</Text>
          <TouchableOpacity onPress={() => router.replace('/')} style={s.homeBtn}>
            <Text style={s.homeBtnText}>{t('common.back')}</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const online      = isFullTriage(session);
  const diagnosis   = online ? session.diagnosis : session as OfflinePrediction;
  const triageLevel = online ? session.triage.level as TriageLevel : undefined;
  const triage      = online ? session.triage : undefined;
  const cfg         = triageLevel ? TRIAGE_CONFIG[triageLevel] : null;
  const confidence  = Math.round(diagnosis.confidence * 100);
  const confLabel   = confidence >= 70 ? 'High' : confidence >= 45 ? 'Moderate' : 'Low';
  const diagSource: string = online ? (diagnosis.diagnosis_source ?? 'xgboost') : 'tflite_offline';

  async function handleShare() {
    await Share.share({
      message: [
        'Vaidya Health Assessment',
        `Condition: ${diagnosis.primary_diagnosis}`,
        `Confidence: ${confidence}%`,
        cfg ? `Triage: ${cfg.label}` : '',
        '',
        t('common.disclaimer'),
      ].filter(Boolean).join('\n'),
    });
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* ── Header ───────────────────────────────────────────────── */}
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} accessibilityLabel="Go back">
            <View style={s.backCircle}>
              <Text style={s.backGlyph}>←</Text>
            </View>
          </TouchableOpacity>
          <Text style={s.headerTitle}>ASSESSMENT</Text>
          <TouchableOpacity onPress={handleShare} style={s.shareBtn}>
            <Text style={s.shareText}>Share</Text>
          </TouchableOpacity>
        </View>

        {/* ── Triage banner (full-bleed) ───────────────────────────── */}
        {cfg && triageLevel && (
          <Animated.View
            entering={FadeInUp.duration(440)}
            style={[s.triageBanner, { backgroundColor: cfg.bgColor, borderColor: cfg.borderColor }]}
          >
            <View style={[s.triageLevelBadge, { backgroundColor: cfg.color }]}>
              <Text style={s.triageLevelNum}>L{triageLevel}</Text>
            </View>
            <View style={s.triageBannerBody}>
              <TriageTag level={triageLevel} size="md" />
              {triage?.reasoning ? (
                <Text style={[s.triageReasoning, { color: cfg.color }]} numberOfLines={3}>
                  {triage.reasoning}
                </Text>
              ) : null}
            </View>
          </Animated.View>
        )}

        {/* ── Emergency — shown immediately if level 4/5 ───────────── */}
        {triageLevel && triageLevel >= 4 && (
          <Animated.View entering={FadeInDown.duration(350).delay(60)} style={{ marginBottom: 10 }}>
            <ActionButton
              label={`${t('common.call_emergency')} · Emergency`}
              onPress={async () => {
                await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
                Linking.openURL('tel:108');
              }}
              variant="danger"
              fullWidth
            />
          </Animated.View>
        )}

        {/* ── ASHA worker card ────────────────────────────────────── */}
        {online && triage?.asha_assigned && (
          <Animated.View entering={FadeInDown.duration(350).delay(80)}>
            <GradientCard style={s.ashaCard}>
              <View style={s.ashaRow}>
                <View style={s.ashaAvatar}>
                  <Text style={s.ashaAvatarText}>
                    {(triage.asha_assigned.name ?? '?').charAt(0).toUpperCase()}
                  </Text>
                </View>
                <View style={s.ashaInfo}>
                  <PillBadge label="ASHA · Notified" color={COLORS.sage} bg={COLORS.sageGhost} size="sm" />
                  <Text style={s.ashaName}>{triage.asha_assigned.name}</Text>
                  <Text style={s.ashaMeta}>
                    {triage.asha_assigned.distance_km} km · {triage.asha_assigned.village}
                  </Text>
                </View>
                <TouchableOpacity
                  style={s.ashaCallBtn}
                  onPress={async () => {
                    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                    Linking.openURL(`tel:${triage.asha_assigned!.phone}`);
                  }}
                >
                  <Text style={s.ashaCallText}>Call</Text>
                </TouchableOpacity>
              </View>
            </GradientCard>
          </Animated.View>
        )}

        {/* ── Red flags ───────────────────────────────────────────── */}
        {(diagnosis as DiagnosisResult).red_flags?.length > 0 && (
          <Animated.View entering={FadeInDown.duration(350).delay(100)}>
            <GradientCard tint="rgba(194,59,34,0.04)" style={s.redFlagCard}>
              <SectionHeader title={t('result.red_flags_label')} />
              {(diagnosis as DiagnosisResult).red_flags.map((flag, i) => (
                <View key={i} style={s.flagRow}>
                  <View style={s.flagDot} />
                  <Text style={s.flagText}>{flag}</Text>
                </View>
              ))}
            </GradientCard>
          </Animated.View>
        )}

        {/* ── Low confidence warning ──────────────────────────────── */}
        {diagnosis.confidence < 0.60 && !bannerDismissed && (
          <Animated.View entering={FadeInDown} style={s.lowConfBanner}>
            <Text style={s.lowConfText}>{t('result.low_confidence_banner')}</Text>
            <TouchableOpacity onPress={() => setBannerDismissed(true)} style={s.lowConfDismiss}>
              <Text style={s.lowConfDismissText}>×</Text>
            </TouchableOpacity>
          </Animated.View>
        )}

        {/* ── Primary diagnosis card ───────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(350).delay(130)}>
          <GradientCard variant="elevated">
            <Text style={s.cardLabel}>{t('result.diagnosis_label').toUpperCase()}</Text>
            <Text style={s.diagName}>{diagnosis.primary_diagnosis}</Text>

            {diagnosis.confidence >= 0.80 && (
              <View style={s.highConfChipWrap}>
                <PillBadge
                  label={t('result.high_confidence_chip')}
                  color={COLORS.success}
                  bg={COLORS.successLight}
                  size="sm"
                />
              </View>
            )}

            {/* Confidence with ring + bar */}
            <View style={s.confSection}>
              <ScoreRing confidence={confidence} color={cfg?.color ?? COLORS.sage} />
              <View style={s.confDetails}>
                <Text style={s.confMetaLabel}>{t('result.confidence_label')}</Text>
                <Text style={[s.confValueLabel, { color: cfg?.color ?? COLORS.sage }]}>{confLabel}</Text>
                <AnimatedConfidenceBar value={confidence} color={cfg?.color ?? COLORS.sage} delay={300} />
              </View>
            </View>

            <View style={s.sourceSep}>
              <PillBadge
                label={SOURCE_LABELS[diagSource] ?? diagSource}
                color={COLORS.textMuted}
                bg={COLORS.inkGhost}
                size="sm"
              />
            </View>
          </GradientCard>
        </Animated.View>

        {/* ── Audio result ────────────────────────────────────────── */}
        {online && (session as FullTriageResponse).audio_result && (
          <Animated.View entering={FadeInDown.duration(350).delay(160)}>
            <GradientCard>
              <Text style={s.cardLabel}>{t('audio_result.title').toUpperCase()}</Text>
              <Text style={s.diagName}>{(session as FullTriageResponse).audio_result?.top_prediction?.label || 'Respiratory assessment'}</Text>
              <View style={s.confRow}>
                <Text style={s.confMetaLabel}>{t('result.confidence_label')}</Text>
                <AnimatedConfidenceBar
                  value={Math.round(((session as FullTriageResponse).audio_result?.top_prediction?.confidence || 0) * 100)}
                  color={COLORS.sage}
                  delay={400}
                />
              </View>
            </GradientCard>
          </Animated.View>
        )}

        {/* ── Vision result ───────────────────────────────────────── */}
        {online && (session as FullTriageResponse).vision_result && (() => {
          const vr       = (session as FullTriageResponse).vision_result;
          const topPred  = vr?.top_prediction;
          const topLabel = typeof topPred === 'string' ? topPred : (topPred?.label ?? 'Pathology detected');
          const topConf  = typeof topPred === 'object' && topPred?.confidence != null
            ? Math.round(topPred.confidence * 100)
            : Math.round((vr?.all_predictions?.[0]?.confidence ?? 0.85) * 100);
          return (
            <Animated.View entering={FadeInDown.duration(350).delay(180)}>
              <GradientCard>
                <Text style={s.cardLabel}>{t('image_result.title').toUpperCase()}</Text>
                <Text style={s.diagName}>{topLabel}</Text>
                <View style={s.confRow}>
                  <Text style={s.confMetaLabel}>{t('result.confidence_label')}</Text>
                  <AnimatedConfidenceBar value={topConf} color={COLORS.sage} delay={450} />
                </View>
                {!!vr?.gemini_description && (
                  <View style={s.visionGeminiWrap}>
                    <View style={s.geminiHeader}>
                      <Text style={s.cardLabel}>GEMINI VISION ANALYSIS</Text>
                      <View style={s.geminiBadge}>
                        <Text style={s.geminiBadgeText}>✦ Gemini</Text>
                      </View>
                    </View>
                    <Text style={s.geminiText}>{vr.gemini_description}</Text>
                  </View>
                )}
              </GradientCard>
            </Animated.View>
          );
        })()}

        {/* ── Fusion detail button ─────────────────────────────────── */}
        {online && ((session as FullTriageResponse).audio_result || (session as FullTriageResponse).vision_result) && (
          <Animated.View entering={FadeInDown.duration(350).delay(195)}>
            <TouchableOpacity style={s.fusionBtn} onPress={() => router.push('/fusion-detail')}>
              <Text style={s.fusionBtnText}>How was this diagnosed?  ›</Text>
            </TouchableOpacity>
          </Animated.View>
        )}

        {/* ── About this condition ─────────────────────────────────── */}
        {online && (diagnosis as DiagnosisResult).description ? (
          <Animated.View entering={FadeInDown.duration(350).delay(200)}>
            <GradientCard>
              <Text style={s.cardLabel}>{t('result.description_label').toUpperCase()}</Text>
              <Text style={s.descText}>{(diagnosis as DiagnosisResult).description}</Text>
            </GradientCard>
          </Animated.View>
        ) : null}

        {/* ── Gemini AI health guide ───────────────────────────────── */}
        {online && (diagnosis as DiagnosisResult).gemini_explanation ? (
          <Animated.View entering={FadeInDown.duration(350).delay(215)}>
            <GradientCard>
              <View style={s.geminiHeader}>
                <Text style={s.cardLabel}>AI HEALTH GUIDE</Text>
                <View style={s.geminiBadge}>
                  <Text style={s.geminiBadgeText}>✦ Gemini</Text>
                </View>
              </View>
              <Text style={s.geminiText}>{(diagnosis as DiagnosisResult).gemini_explanation}</Text>
            </GradientCard>
          </Animated.View>
        ) : null}

        {/* ── Top 3 diagnoses (primary + differential) ────────────── */}
        <Animated.View entering={FadeInDown.duration(350).delay(230)}>
          <GradientCard>
            <Text style={s.cardLabel}>TOP 3 DIAGNOSES</Text>
            {/* Rank 1 — primary */}
            <View style={s.diffRow}>
              <View style={[s.diffRank, { backgroundColor: cfg?.color ?? COLORS.sage, borderColor: cfg?.color ?? COLORS.sage }]}>
                <Text style={[s.diffRankText, { color: '#fff' }]}>1</Text>
              </View>
              <View style={s.diffBody}>
                <Text style={[s.diffName, { fontWeight: '700', color: COLORS.ink }]} numberOfLines={1}>
                  {diagnosis.primary_diagnosis}
                </Text>
                <AnimatedConfidenceBar value={confidence} color={cfg?.color ?? COLORS.sage} delay={300} />
              </View>
            </View>
            {/* Ranks 2–4 from differential */}
            {(diagnosis.differential ?? []).slice(0, 3).map((d, i) => {
              const pct = Math.round(d.confidence * 100);
              return (
                <View key={i} style={s.diffRow}>
                  <View style={s.diffRank}>
                    <Text style={s.diffRankText}>{i + 2}</Text>
                  </View>
                  <View style={s.diffBody}>
                    <Text style={s.diffName} numberOfLines={1}>{d.disease}</Text>
                    <AnimatedConfidenceBar value={pct} color={COLORS.inkSoft} delay={380 + i * 80} />
                  </View>
                </View>
              );
            })}
          </GradientCard>
        </Animated.View>

        {/* ── Precautions ─────────────────────────────────────────── */}
        {online && (diagnosis as DiagnosisResult).precautions?.length > 0 && (
          <Animated.View entering={FadeInDown.duration(350).delay(260)}>
            <GradientCard>
              <Text style={s.cardLabel}>{t('result.precautions_label').toUpperCase()}</Text>
              {(diagnosis as DiagnosisResult).precautions.map((p, i) => (
                <View key={i} style={s.precRow}>
                  <View style={s.precNum}>
                    <Text style={s.precNumText}>{i + 1}</Text>
                  </View>
                  <Text style={s.precText}>{p}</Text>
                </View>
              ))}
            </GradientCard>
          </Animated.View>
        )}

        {/* ── Action buttons (stacked) ─────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(350).delay(300)} style={s.actionStack}>
          <ActionButton
            label={`${t('result.find_care')}  →`}
            onPress={() => router.push('/care')}
            variant="primary"
            fullWidth
          />
          <View style={s.actionRow}>
            <ActionButton label={t('result.new_check')} onPress={() => { useAppStore.getState().resetInput(); router.replace('/symptom' as any); }} variant="secondary" />
            <ActionButton label={t('common.back')}      onPress={() => router.replace('/')}        variant="outline" />
          </View>
        </Animated.View>

        {/* ── Disclaimer ──────────────────────────────────────────── */}
        <View style={s.disclaimerWrap}>
          <View style={s.disclaimerRule} />
          <Text style={s.disclaimer}>{t('common.disclaimer')}</Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { paddingHorizontal: 20, paddingBottom: 52, paddingTop: 8 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },

  errorText:  { ...TYPE.bodyMed, color: COLORS.textMuted, marginBottom: 16 },
  homeBtn:    { backgroundColor: COLORS.ink, borderRadius: RADIUS.lg, paddingVertical: 14, paddingHorizontal: 24 },
  homeBtnText:{ ...TYPE.titleLarge, color: COLORS.textInverse },

  // Header
  header:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14, marginBottom: 12 },
  backBtn:    { width: scale(40), height: scale(40), justifyContent: 'center' },
  backCircle: { width: scale(34), height: scale(34), borderRadius: scale(17), backgroundColor: COLORS.parchmentWarm, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backGlyph:  { fontSize: 17, color: COLORS.ink, marginTop: -1 },
  headerTitle:{ ...TYPE.micro, color: COLORS.textMuted, letterSpacing: 2, fontWeight: '700' },
  shareBtn:   { padding: 4 },
  shareText:  { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '600' },

  // Triage banner
  triageBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 14,
    borderRadius: RADIUS.xl,
    borderWidth: 1.5,
    padding: 18,
    marginBottom: 12,
  },
  triageLevelBadge:  { width: 44, height: 44, borderRadius: RADIUS.md, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  triageLevelNum:    { fontSize: 12, fontWeight: '800', color: '#fff', letterSpacing: 0.5 },
  triageBannerBody:  { flex: 1, gap: 8 },
  triageReasoning:   { ...TYPE.bodySmall, lineHeight: 20, marginTop: 4, opacity: 0.85 },

  // ASHA
  ashaCard: { marginBottom: 10 },
  ashaRow:  { flexDirection: 'row', alignItems: 'center', gap: 12 },
  ashaAvatar:    { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.sageGhost, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)' },
  ashaAvatarText:{ fontSize: 17, fontWeight: '700', color: COLORS.sage },
  ashaInfo:      { flex: 1, gap: 4 },
  ashaName:      { ...TYPE.titleMed, color: COLORS.ink },
  ashaMeta:      { ...TYPE.micro, color: COLORS.textFaint },
  ashaCallBtn:   { backgroundColor: COLORS.sage, borderRadius: RADIUS.md, paddingHorizontal: 16, paddingVertical: 10 },
  ashaCallText:  { ...TYPE.titleMed, color: '#fff' },

  // Red flags
  redFlagCard:  { borderWidth: 1, borderColor: 'rgba(194,59,34,0.2)', marginBottom: 10 },
  flagRow:      { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  flagDot:      { width: 5, height: 5, borderRadius: 3, backgroundColor: COLORS.crimson, flexShrink: 0 },
  flagText:     { ...TYPE.bodySmall, color: COLORS.crimsonDeep, flex: 1, lineHeight: 20 },

  // Diagnosis card
  cardLabel:     { ...TYPE.micro, color: COLORS.textFaint, letterSpacing: 1.5, marginBottom: 10, fontWeight: '700' },
  diagName:      { fontSize: mScale(23), fontWeight: '700', letterSpacing: -0.5, color: COLORS.ink, marginBottom: 14, lineHeight: mScale(30) },
  highConfChipWrap: { marginBottom: 14 },

  // Confidence section
  confSection:   { flexDirection: 'row', alignItems: 'center', gap: 18, marginBottom: 14 },
  confDetails:   { flex: 1, gap: 6 },
  confMetaLabel: { ...TYPE.micro, color: COLORS.textFaint },
  confValueLabel:{ ...TYPE.titleMed, fontWeight: '700' },
  confRow:       { flexDirection: 'row', alignItems: 'center', gap: 10 },

  sourceSep:     { borderTopWidth: 1, borderTopColor: COLORS.border, paddingTop: 12 },
  descText:      { ...TYPE.bodyMed, color: COLORS.textSub, lineHeight: 24 },

  // Gemini Vision section (inside vision card)
  visionGeminiWrap: { marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: COLORS.border },

  // Gemini AI health guide
  geminiHeader:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  geminiBadge:     { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(66,133,244,0.08)', borderRadius: RADIUS.pill, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: 'rgba(66,133,244,0.18)' },
  geminiBadgeText: { fontSize: 10, fontWeight: '700', color: '#4285F4', letterSpacing: 0.3 },
  geminiText:      { ...TYPE.bodyMed, color: COLORS.textSub, lineHeight: 24 },

  // Differential
  diffRow:      { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  diffRank:     { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  diffRankText: { fontSize: 10, fontWeight: '700', color: COLORS.textMuted },
  diffBody:     { flex: 1, gap: 5 },
  diffName:     { ...TYPE.bodySmall, color: COLORS.textSub, fontWeight: '500' },

  // Precautions
  precRow:     { flexDirection: 'row', gap: 12, marginBottom: 12, alignItems: 'flex-start' },
  precNum:     { width: 22, height: 22, borderRadius: 11, borderWidth: 1.5, borderColor: COLORS.borderMid, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  precNumText: { fontSize: 10, fontWeight: '700', color: COLORS.textMuted },
  precText:    { ...TYPE.bodySmall, color: COLORS.textSub, flex: 1, lineHeight: 21 },

  // Action buttons
  actionStack:  { gap: 10, marginBottom: 10 },
  actionRow:    { flexDirection: 'row', gap: 10 },
  actionBtn:    { borderRadius: RADIUS.lg, paddingVertical: 18, alignItems: 'center', justifyContent: 'center' },
  actionBtnText:{ ...TYPE.titleLarge, fontSize: 15 },

  fusionBtn:     { backgroundColor: COLORS.parchmentWarm, borderRadius: RADIUS.lg, paddingVertical: 14, alignItems: 'center', marginBottom: 0, borderWidth: 1, borderColor: COLORS.border },
  fusionBtnText: { ...TYPE.titleMed, color: COLORS.textSub },

  // Disclaimer
  disclaimerWrap: { paddingTop: 24, gap: 12, alignItems: 'center' },
  disclaimerRule: { width: 24, height: 1, backgroundColor: COLORS.border },
  disclaimer:     { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', lineHeight: 18, maxWidth: 300 },

  // Low confidence
  lowConfBanner: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.warningLight,
    borderLeftWidth: 3, borderLeftColor: COLORS.warning,
    borderColor: 'rgba(154,107,31,0.20)', borderWidth: 1,
    borderRadius: RADIUS.md, padding: 14, marginBottom: 10,
  },
  lowConfText:        { ...TYPE.bodySmall, color: COLORS.gold, flex: 1, lineHeight: 20 },
  lowConfDismiss:     { paddingLeft: 10 },
  lowConfDismissText: { fontSize: 18, color: COLORS.gold, fontWeight: '400', lineHeight: 20 },
});
