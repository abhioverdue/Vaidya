/**
 * Vaidya — Home screen  (v3 · Senior Apple Designer Redesign)
 * Premium: animated waveform hero, pulsing emergency, stat chips, spring interactions
 */

import {
  View, Text, TouchableOpacity, ScrollView,
  StyleSheet, Linking, Pressable,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import Animated, {
  FadeIn, FadeInDown,
  useAnimatedStyle, useSharedValue,
  withSpring, withRepeat, withTiming, withSequence, withDelay,
  interpolate, Easing, cancelAnimation,
} from 'react-native-reanimated';
import { useCallback, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { COLORS, TRIAGE_CONFIG, TYPE, RADIUS, STORAGE_KEYS } from '@/constants';
import { mScale, vScale } from '@/utils/responsive';
import { OfflineBanner } from '@/components/ui/OfflineBanner';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { TriageTag } from '@/components/ui/TriageTag';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { useDemoMode } from '@/hooks/useDemoMode';
import { getSessionCount, checkOutbreakSignal, type OutbreakSignal } from '@/services/firestore';
import type { TriageLevel, TriageSession } from '@/types';

function getGreetingKey(): 'greeting_morning' | 'greeting_afternoon' | 'greeting_evening' {
  const h = new Date().getHours();
  if (h < 12) return 'greeting_morning';
  if (h < 17) return 'greeting_afternoon';
  return 'greeting_evening';
}

// ── WaveBar — single animated bar in the EQ waveform ────────────────────────

function WaveBar({
  targetHeight,
  delay,
  color = COLORS.sage,
  width: barW = 3,
}: {
  targetHeight: number;
  delay: number;
  color?: string;
  width?: number;
}) {
  const height = useSharedValue(3);

  useEffect(() => {
    height.value = withDelay(
      delay,
      withRepeat(
        withSequence(
          withTiming(targetHeight, { duration: 500 + delay % 300, easing: Easing.inOut(Easing.sin) }),
          withTiming(3, { duration: 500 + delay % 300, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
        false,
      ),
    );
    return () => cancelAnimation(height);
  }, []);

  const animStyle = useAnimatedStyle(() => ({ height: height.value }));

  return (
    <Animated.View
      style={[
        { width: barW, borderRadius: barW, backgroundColor: color },
        animStyle,
      ]}
    />
  );
}

// ── HeroWaveform — decorative EQ bars in the hero ───────────────────────────

const WAVE_HEIGHTS = [8, 16, 22, 30, 20, 36, 18, 28, 14, 32, 10, 26, 20, 14, 28, 18, 24, 12, 20, 16];

function HeroWaveform() {
  return (
    <View style={hw.row}>
      {WAVE_HEIGHTS.map((h, i) => (
        <WaveBar
          key={i}
          targetHeight={h}
          delay={i * 80}
          color={i % 3 === 0 ? COLORS.sageLight : i % 3 === 1 ? COLORS.sage : COLORS.sageDark}
          width={3}
        />
      ))}
    </View>
  );
}

const hw = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    height: vScale(40),
    marginTop: vScale(16),
    marginBottom: 4,
  },
});

// ── StatChip — horizontal capability chip ────────────────────────────────────

function StatChip({ label, dot }: { label: string; dot: string }) {
  return (
    <View style={sc.chip}>
      <Text style={sc.dot}>{dot}</Text>
      <Text style={sc.label}>{label}</Text>
    </View>
  );
}

const sc = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.pill,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  dot:   { fontSize: 8, color: COLORS.sage },
  label: { ...TYPE.micro, color: COLORS.textSub, fontWeight: '600', letterSpacing: 0.3 },
});

// ── PulsingRing — two concentric rings that pulse outward ────────────────────

function PulsingRing({ color, size }: { color: string; size: number }) {
  const ring1 = useSharedValue(0);
  const ring2 = useSharedValue(0);

  useEffect(() => {
    ring1.value = withRepeat(withTiming(1, { duration: 1800, easing: Easing.out(Easing.quad) }), -1, false);
    ring2.value = withDelay(900, withRepeat(withTiming(1, { duration: 1800, easing: Easing.out(Easing.quad) }), -1, false));
    return () => { cancelAnimation(ring1); cancelAnimation(ring2); };
  }, []);

  const r1Style = useAnimatedStyle(() => ({
    position: 'absolute',
    width: size,
    height: size,
    borderRadius: size / 2,
    borderWidth: 1.5,
    borderColor: color,
    opacity: interpolate(ring1.value, [0, 1], [0.6, 0]),
    transform: [{ scale: interpolate(ring1.value, [0, 1], [1, 2.2]) }],
  }));

  const r2Style = useAnimatedStyle(() => ({
    position: 'absolute',
    width: size,
    height: size,
    borderRadius: size / 2,
    borderWidth: 1.5,
    borderColor: color,
    opacity: interpolate(ring2.value, [0, 1], [0.6, 0]),
    transform: [{ scale: interpolate(ring2.value, [0, 1], [1, 2.2]) }],
  }));

  return (
    <>
      <Animated.View style={r1Style} />
      <Animated.View style={r2Style} />
    </>
  );
}

// ── QuickActionCard ───────────────────────────────────────────────────────────

interface QuickActionProps {
  title: string;
  subtitle: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  tag?: string;
  showWave?: boolean;
}

function QuickActionCard({ title, subtitle, onPress, variant = 'secondary', tag, showWave }: QuickActionProps) {
  const scale = useSharedValue(1);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const onPressIn  = useCallback(() => { scale.value = withSpring(0.97, { damping: 20, stiffness: 300 }); }, []);
  const onPressOut = useCallback(() => { scale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }, []);

  const isPrimary = variant === 'primary';

  return (
    <Animated.View style={aStyle}>
      <Pressable
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        onPress={async () => { await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onPress(); }}
        style={[styles.qCard, isPrimary ? styles.qCardPrimary : styles.qCardSecondary]}
      >
        {/* Top row: tag + arrow */}
        <View style={styles.qCardTopRow}>
          {tag ? (
            <View style={[styles.qCardTagPill, isPrimary && styles.qCardTagPillPrimary]}>
              <Text style={[styles.qCardTagText, isPrimary && styles.qCardTagTextPrimary]}>
                {tag.toUpperCase()}
              </Text>
            </View>
          ) : <View />}
          <View style={[styles.qCardArrow, isPrimary && styles.qCardArrowPrimary]}>
            <Text style={[styles.qCardArrowGlyph, isPrimary && styles.qCardArrowGlyphPrimary]}>↗</Text>
          </View>
        </View>

        {/* Wave decoration inside primary card */}
        {isPrimary && showWave && (
          <View style={styles.qCardWave}>
            <HeroWaveform />
          </View>
        )}

        {/* Text */}
        <View style={styles.qCardTextBlock}>
          <Text style={[styles.qCardTitle, isPrimary && styles.qCardTitlePrimary]}>{title}</Text>
          <Text style={[styles.qCardSub,   isPrimary && styles.qCardSubPrimary]}>{subtitle}</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

// ── SessionRow ────────────────────────────────────────────────────────────────

function SessionRow({ session, index }: { session: TriageSession; index: number }) {
  const result    = session.result;
  const isPrimary = 'primary_diagnosis' in result;
  const triage    = 'triage' in result ? (result as any).triage?.level as TriageLevel : undefined;
  const dx        = isPrimary ? result.primary_diagnosis : '—';
  const conf      = isPrimary ? Math.round((result as any).confidence * 100) : null;
  const date      = new Date(session.timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  const accentColor = triage ? TRIAGE_CONFIG[triage].color : COLORS.border;

  function openSession() {
    useAppStore.getState().setCurrentSession(session.result);
    router.push('/result' as any);
  }

  return (
    <Animated.View entering={FadeInDown.duration(280).delay(index * 55)}>
      <TouchableOpacity style={styles.sessionRow} activeOpacity={0.72} onPress={openSession}>
        <View style={[styles.sessionAccent, { backgroundColor: accentColor }]} />
        <View style={styles.sessionContent}>
          <Text style={styles.sessionDx} numberOfLines={1}>{dx}</Text>
          <View style={styles.sessionMetaRow}>
            <Text style={styles.sessionMeta}>{date}</Text>
            <View style={styles.sessionDot} />
            <Text style={styles.sessionMeta}>{session.was_offline ? 'offline' : 'online'}</Text>
            {conf !== null && (
              <>
                <View style={styles.sessionDot} />
                <Text style={[styles.sessionMeta, { color: accentColor, fontWeight: '600' }]}>{conf}%</Text>
              </>
            )}
          </View>
        </View>
        <View style={styles.sessionRight}>
          {triage ? <TriageTag level={triage} size="sm" /> : null}
        </View>
      </TouchableOpacity>
    </Animated.View>
  );
}

// ── HomeScreen ────────────────────────────────────────────────────────────────

export default function HomeScreen() {
  const { t }      = useTranslation();
  const sessions   = useAppStore((s) => s.sessionHistory);
  const isOnline   = useAppStore((s) => s.isOnline);
  const isDemoMode = useDemoMode();

  const [globalCount,    setGlobalCount]    = useState<number | null>(null);
  const [outbreakSignal, setOutbreakSignal] = useState<OutbreakSignal | null>(null);
  useEffect(() => {
    getSessionCount().then(setGlobalCount).catch(() => {});
    checkOutbreakSignal(48, 5).then(setOutbreakSignal).catch(() => {});
  }, []);

  // Emergency button pulse
  const emergencyScale = useSharedValue(1);
  useEffect(() => {
    emergencyScale.value = withRepeat(
      withSequence(
        withTiming(1.08, { duration: 900, easing: Easing.inOut(Easing.sin) }),
        withTiming(1,    { duration: 900, easing: Easing.inOut(Easing.sin) }),
      ),
      -1, false,
    );
    return () => cancelAnimation(emergencyScale);
  }, []);
  const emergencyDotStyle = useAnimatedStyle(() => ({ transform: [{ scale: emergencyScale.value }] }));

  const isAuthenticated = useAppStore((s) => s.isAuthenticated);
  const isReady         = useAppStore((s) => s.isReady);

  useEffect(() => {
    if (!isReady) return;
    async function checkOnboarding() {
      const lang = await AsyncStorage.getItem(STORAGE_KEYS.LANGUAGE);
      if (!lang) { router.replace('/language-select'); return; }
      const consent = await AsyncStorage.getItem(STORAGE_KEYS.CONSENT_GIVEN);
      if (!consent) { router.replace('/consent'); return; }
      if (!isAuthenticated) { router.replace('/login' as any); }
    }
    checkOnboarding();
  }, [isAuthenticated, isReady]);

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {!isOnline && <OfflineBanner />}
        {isDemoMode && isOnline && <DemoBanner />}

        {/* ── Top bar ─────────────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(380)} style={styles.topBar}>
          <View style={styles.wordmarkRow}>
            <View style={styles.wordmarkDot} />
            <Text style={styles.wordmark}>VAIDYA</Text>
          </View>
          <View style={styles.topRight}>
            <StatusIndicator online={isOnline} />
            <TouchableOpacity
              onPress={() => router.push('/settings')}
              style={styles.settingsBtn}
              accessibilityLabel="Open settings"
            >
              <View style={styles.burger}>
                <View style={styles.burgerLine} />
                <View style={[styles.burgerLine, { width: 12 }]} />
                <View style={styles.burgerLine} />
              </View>
            </TouchableOpacity>
          </View>
        </Animated.View>

        {/* ── Hero ────────────────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(460).delay(60)} style={styles.hero}>
          <Text style={styles.greeting}>{t(`home.${getGreetingKey()}`)}</Text>
          <Text style={styles.heroTitle}>How are you{'\n'}feeling today?</Text>
          <HeroWaveform />
          <Text style={styles.heroMeta}>
            {isOnline
              ? 'Gemini AI · XGBoost · 132 conditions'
              : 'On-device TFLite · no network needed'}
          </Text>
        </Animated.View>

        {/* ── Stats chips ─────────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(380).delay(100)} style={styles.statsRow}>
          <StatChip dot="●" label="132 conditions" />
          <StatChip dot="◎" label="AI-powered" />
          <StatChip dot="◈" label="3 languages" />
          {globalCount !== null && globalCount > 0
            ? <StatChip dot="◉" label={`${globalCount.toLocaleString()} sessions`} />
            : <StatChip dot="◉" label="Offline ready" />}
        </Animated.View>

        {/* ── Primary CTA ─────────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(400).delay(140)} style={{ marginBottom: 10 }}>
          <QuickActionCard
            title="Check symptoms"
            subtitle="Voice · Text · Image · AI Diagnosis"
            tag={isOnline ? 'AI-powered' : 'Offline'}
            onPress={() => router.push('/symptom')}
            variant="primary"
            showWave={false}
          />
        </Animated.View>

        {/* ── Secondary grid ──────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(400).delay(190)} style={styles.secondaryRow}>
          <View style={styles.half}>
            <QuickActionCard title="Find care" subtitle="PHC · CHC · Hospital" onPress={() => router.push('/care')} />
          </View>
          <View style={styles.half}>
            <QuickActionCard title="Settings" subtitle="Language · Profile" onPress={() => router.push('/settings')} />
          </View>
        </Animated.View>

        {/* ── Outbreak alert (community crisis signal) ────────────────── */}
        {outbreakSignal && (
          <Animated.View entering={FadeInDown.duration(360).delay(220)}>
            <TouchableOpacity
              style={styles.outbreakBanner}
              onPress={() => router.push('/symptom')}
              activeOpacity={0.85}
            >
              <View style={styles.outbreakLeft}>
                <Text style={styles.outbreakIcon}>⚠</Text>
                <View style={styles.outbreakBody}>
                  <Text style={styles.outbreakTitle}>Community Alert</Text>
                  <Text style={styles.outbreakSub}>
                    {outbreakSignal.count} cases of {outbreakSignal.diagnosis} reported in the last {outbreakSignal.hours}h
                  </Text>
                </View>
              </View>
              <Text style={styles.outbreakArrow}>›</Text>
            </TouchableOpacity>
          </Animated.View>
        )}

        {/* ── Emergency strip ─────────────────────────────────────────── */}
        <Animated.View entering={FadeInDown.duration(400).delay(240)}>
          <TouchableOpacity
            style={styles.emergency}
            onPress={async () => {
              await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
              Linking.openURL('tel:108');
            }}
            activeOpacity={0.85}
          >
            <View style={styles.emergencyLeft}>
              {/* Pulsing dot with rings */}
              <View style={styles.emergencyDotWrap}>
                <PulsingRing color={COLORS.crimson} size={10} />
                <Animated.View style={[styles.emergencyDot, emergencyDotStyle]} />
              </View>
              <View>
                <Text style={styles.emergencyTitle}>{t('home.emergency_banner')}</Text>
                <Text style={styles.emergencySub}>Tap to call Ambulance · 108</Text>
              </View>
            </View>
            <View style={styles.emergencyPill}>
              <Text style={styles.emergencyPillText}>108</Text>
            </View>
          </TouchableOpacity>
        </Animated.View>

        {/* ── Recent checks ───────────────────────────────────────────── */}
        {sessions.length > 0 && (
          <Animated.View entering={FadeInDown.duration(400).delay(300)}>
            <SectionHeader
              title="Recent checks"
              badge={sessions.length}
              action={{ label: 'Clear', onPress: () => useAppStore.getState().clearHistory() }}
            />
            {sessions.slice(0, 5).map((s, i) => (
              <SessionRow key={s.id} session={s} index={i} />
            ))}
          </Animated.View>
        )}

        {sessions.length === 0 && (
          <Animated.View entering={FadeIn.duration(600).delay(380)} style={styles.empty}>
            <View style={styles.emptyRule} />
            <Text style={styles.emptyTitle}>No checks yet</Text>
            <Text style={styles.emptyBody}>
              Tap "Check symptoms" to begin your first AI-assisted health assessment.
            </Text>
          </Animated.View>
        )}

        {/* ── Footer ──────────────────────────────────────────────────── */}
        <View style={styles.footerWrap}>
          <View style={styles.footerRule} />
          <Text style={styles.footer}>
            Gemini AI + TFLite offline · Not a substitute for professional medical advice
          </Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { paddingHorizontal: 20, paddingBottom: 52, paddingTop: 8 },

  // Top bar
  topBar:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 16, marginBottom: 4 },
  wordmarkRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  wordmarkDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: COLORS.sage },
  wordmark:    { fontSize: 13, fontWeight: '700', letterSpacing: 4, color: COLORS.ink },
  topRight:    { flexDirection: 'row', alignItems: 'center', gap: 10 },
  settingsBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  burger:      { gap: 4, alignItems: 'flex-end' },
  burgerLine:  { height: 1.5, width: 18, backgroundColor: COLORS.inkSoft, borderRadius: 1 },

  // Hero
  hero:      { marginBottom: 16, paddingTop: 8 },
  greeting:  { ...TYPE.micro, color: COLORS.sage, letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 10, fontWeight: '700' },
  heroTitle: { fontSize: mScale(38), fontWeight: '700', letterSpacing: -1.2, lineHeight: mScale(44), color: COLORS.ink, marginBottom: 2 },
  heroMeta:  { ...TYPE.bodySmall, color: COLORS.textMuted, marginTop: 6 },

  // Stats chips
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },

  // Quick-action cards
  qCard:          { borderRadius: RADIUS.xl, padding: 20, overflow: 'hidden' },
  qCardPrimary:   { backgroundColor: COLORS.ink, minHeight: vScale(150) },
  qCardSecondary: {
    backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
    shadowColor: COLORS.ink,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },

  qCardTopRow:         { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  qCardTagPill:        { backgroundColor: 'rgba(58,95,82,0.18)', borderRadius: RADIUS.pill, paddingHorizontal: 8, paddingVertical: 3 },
  qCardTagPillPrimary: { backgroundColor: 'rgba(255,255,255,0.14)' },
  qCardTagText:        { ...TYPE.micro, color: COLORS.sage, fontWeight: '700', letterSpacing: 0.8 },
  qCardTagTextPrimary: { color: 'rgba(247,244,238,0.7)' },

  qCardArrow:          { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.inkGhost, alignItems: 'center', justifyContent: 'center' },
  qCardArrowPrimary:   { backgroundColor: 'rgba(255,255,255,0.12)' },
  qCardArrowGlyph:     { fontSize: 15, color: COLORS.ink, fontWeight: '400' },
  qCardArrowGlyphPrimary: { color: COLORS.textInverse },

  qCardWave: { marginVertical: 8, overflow: 'hidden' },

  qCardTextBlock: { marginTop: 'auto' as any, paddingTop: 12 },
  qCardTitle:     { ...TYPE.headlineMed, color: COLORS.ink, marginBottom: 2 },
  qCardTitlePrimary: { color: COLORS.textInverse },
  qCardSub:          { ...TYPE.micro, color: COLORS.textFaint, letterSpacing: 0.3 },
  qCardSubPrimary:   { color: 'rgba(247,244,238,0.5)' },

  secondaryRow: { flexDirection: 'row', gap: 10, marginBottom: 10 },
  half:         { flex: 1 },

  // Outbreak alert
  outbreakBanner: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: 'rgba(154,107,31,0.08)',
    borderRadius: RADIUS.lg, borderWidth: 1.5, borderColor: 'rgba(154,107,31,0.3)',
    padding: 14, marginBottom: 10,
  },
  outbreakLeft:  { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  outbreakIcon:  { fontSize: 20, color: COLORS.gold },
  outbreakBody:  { flex: 1, gap: 2 },
  outbreakTitle: { fontSize: 13, fontWeight: '700', color: COLORS.gold, letterSpacing: 0.2 },
  outbreakSub:   { fontSize: 11, color: COLORS.gold, opacity: 0.85, lineHeight: 16 },
  outbreakArrow: { fontSize: 20, color: COLORS.gold, opacity: 0.6 },

  // Emergency
  emergency:     {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: 'rgba(194,59,34,0.22)',
    paddingVertical: 16, paddingHorizontal: 18,
    marginBottom: 32,
    shadowColor: COLORS.crimson,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  emergencyLeft:    { flexDirection: 'row', alignItems: 'center', gap: 14 },
  emergencyDotWrap: { width: 20, height: 20, alignItems: 'center', justifyContent: 'center' },
  emergencyDot:     { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.crimson },
  emergencyTitle:   { ...TYPE.titleMed, color: COLORS.crimson },
  emergencySub:     { ...TYPE.micro, color: COLORS.crimson, opacity: 0.65, marginTop: 2 },
  emergencyPill:    { backgroundColor: COLORS.crimson, borderRadius: RADIUS.pill, paddingHorizontal: 16, paddingVertical: 8 },
  emergencyPillText:{ fontSize: 14, fontWeight: '800', color: '#fff', letterSpacing: 1 },

  // Session rows
  sessionRow:    { flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  sessionAccent: { width: 4, height: 40, borderRadius: 2 },
  sessionContent:{ flex: 1, gap: 4 },
  sessionDx:     { ...TYPE.titleMed, color: COLORS.ink },
  sessionMetaRow:{ flexDirection: 'row', alignItems: 'center', gap: 6 },
  sessionMeta:   { ...TYPE.micro, color: COLORS.textFaint },
  sessionDot:    { width: 2, height: 2, borderRadius: 1, backgroundColor: COLORS.textFaint },
  sessionRight:  { alignItems: 'flex-end' },

  // Empty state
  empty:      { paddingVertical: 44, alignItems: 'flex-start', gap: 10 },
  emptyRule:  { width: 24, height: 2, backgroundColor: COLORS.borderMid, borderRadius: 1 },
  emptyTitle: { ...TYPE.headlineMed, color: COLORS.ink },
  emptyBody:  { ...TYPE.bodyMed, color: COLORS.textMuted, lineHeight: 22, maxWidth: 280 },

  // Footer
  footerWrap: { alignItems: 'center', gap: 12, marginTop: 24 },
  footerRule: { width: 32, height: 1, backgroundColor: COLORS.border },
  footer:     { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', lineHeight: 18 },
});
