/**
 * Vaidya — Analysis / Loading screen  (v3 · Senior Apple Designer Redesign)
 * Pulsing concentric rings, orbital dots, refined step list with connecting lines.
 */

import { View, Text, StyleSheet } from 'react-native';
import { scale, mScale } from '@/utils/responsive';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useEffect, useMemo } from 'react';
import { router } from 'expo-router';
import Animated, {
  FadeIn, FadeInDown,
  useSharedValue, useAnimatedStyle,
  withRepeat, withTiming, withSequence, withDelay,
  interpolate, Easing, cancelAnimation,
} from 'react-native-reanimated';

import { useAppStore } from '@/store';
import { COLORS, TYPE, RADIUS } from '@/constants';

// ── PulsingRing ───────────────────────────────────────────────────────────────

function PulsingRing({
  size, delay, color = COLORS.sage,
}: { size: number; delay: number; color?: string }) {
  const scale   = useSharedValue(0.85);
  const opacity = useSharedValue(0);

  useEffect(() => {
    scale.value   = withDelay(delay, withRepeat(
      withTiming(1.55, { duration: 2200, easing: Easing.out(Easing.quad) }),
      -1, false,
    ));
    opacity.value = withDelay(delay, withRepeat(
      withSequence(
        withTiming(0.55, { duration: 400 }),
        withTiming(0,    { duration: 1800, easing: Easing.out(Easing.quad) }),
      ),
      -1, false,
    ));
    return () => { cancelAnimation(scale); cancelAnimation(opacity); };
  }, []);

  const style = useAnimatedStyle(() => ({
    position: 'absolute',
    width: size,
    height: size,
    borderRadius: size / 2,
    borderWidth: 1.5,
    borderColor: color,
    opacity: opacity.value,
    transform: [{ scale: scale.value }],
  }));

  return <Animated.View style={style} />;
}

// ── OrbitalDot ────────────────────────────────────────────────────────────────

function OrbitalDot({ radius, startAngle, duration }: { radius: number; startAngle: number; duration: number }) {
  const angle = useSharedValue(startAngle);

  useEffect(() => {
    angle.value = withRepeat(
      withTiming(startAngle + 360, { duration, easing: Easing.linear }),
      -1, false,
    );
    return () => cancelAnimation(angle);
  }, []);

  const style = useAnimatedStyle(() => {
    const rad = (angle.value * Math.PI) / 180;
    const x   = Math.cos(rad) * radius;
    const y   = Math.sin(rad) * radius;
    return {
      position: 'absolute',
      width: 5,
      height: 5,
      borderRadius: 3,
      backgroundColor: COLORS.sage,
      opacity: 0.55,
      transform: [{ translateX: x }, { translateY: y }],
    };
  });

  return <Animated.View style={style} />;
}

// ── CentralOrb ────────────────────────────────────────────────────────────────

function CentralOrb() {
  const breathe = useSharedValue(1);

  useEffect(() => {
    breathe.value = withRepeat(
      withSequence(
        withTiming(1.06, { duration: 1200, easing: Easing.inOut(Easing.sin) }),
        withTiming(1,    { duration: 1200, easing: Easing.inOut(Easing.sin) }),
      ),
      -1, false,
    );
    return () => cancelAnimation(breathe);
  }, []);

  const orbStyle = useAnimatedStyle(() => ({
    transform: [{ scale: breathe.value }],
  }));

  return (
    <View style={co.container}>
      {/* Concentric pulsing rings */}
      <PulsingRing size={100} delay={0}    color={COLORS.sage} />
      <PulsingRing size={100} delay={700}  color={COLORS.sage} />
      <PulsingRing size={100} delay={1400} color={COLORS.sageLight} />

      {/* Orbital dots */}
      <OrbitalDot radius={68} startAngle={0}   duration={4000} />
      <OrbitalDot radius={68} startAngle={120} duration={4000} />
      <OrbitalDot radius={68} startAngle={240} duration={4000} />
      <OrbitalDot radius={52} startAngle={60}  duration={3200} />
      <OrbitalDot radius={52} startAngle={180} duration={3200} />

      {/* Central circle */}
      <Animated.View style={[co.orb, orbStyle]}>
        <View style={co.orbInner}>
          <Text style={co.vMark}>V</Text>
        </View>
      </Animated.View>
    </View>
  );
}

const co = StyleSheet.create({
  container: { width: scale(180), height: scale(180), alignItems: 'center', justifyContent: 'center' },
  orb:       { width: scale(86), height: scale(86), borderRadius: scale(43), backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.22, shadowRadius: 20, elevation: 12 },
  orbInner:  { width: scale(72), height: scale(72), borderRadius: scale(36), borderWidth: 1.5, borderColor: 'rgba(247,244,238,0.15)', alignItems: 'center', justifyContent: 'center' },
  vMark:     { fontSize: mScale(26), fontWeight: '800', color: COLORS.parchment, letterSpacing: 2 },
});

// ── StepRow ───────────────────────────────────────────────────────────────────

type Step = { label: string; detail: string };

function StepRow({ step, active, done, index, isLast }: {
  step: Step; active: boolean; done: boolean; index: number; isLast: boolean;
}) {
  const opacity    = useSharedValue(0);
  const translateX = useSharedValue(-14);

  useEffect(() => {
    opacity.value    = withDelay(index * 140, withTiming(1, { duration: 320 }));
    translateX.value = withDelay(index * 140, withTiming(0, { duration: 320, easing: Easing.out(Easing.quad) }));
  }, []);

  const aStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateX: translateX.value }],
  }));

  // Active dot pulse
  const dotScale = useSharedValue(1);
  useEffect(() => {
    if (active) {
      dotScale.value = withRepeat(
        withSequence(
          withTiming(1.4, { duration: 600, easing: Easing.inOut(Easing.sin) }),
          withTiming(1,   { duration: 600, easing: Easing.inOut(Easing.sin) }),
        ),
        -1, false,
      );
    } else {
      dotScale.value = withTiming(1);
    }
    return () => cancelAnimation(dotScale);
  }, [active]);
  const dotStyle = useAnimatedStyle(() => ({ transform: [{ scale: dotScale.value }] }));

  return (
    <Animated.View style={[st.row, aStyle]}>
      {/* Timeline column */}
      <View style={st.timeline}>
        <Animated.View style={[
          st.mark,
          done   && st.markDone,
          active && st.markActive,
          dotStyle,
        ]}>
          {done   && <View style={st.markCheck} />}
          {active && <View style={st.markActiveDot} />}
        </Animated.View>
        {!isLast && (
          <View style={[st.connector, done && st.connectorDone]} />
        )}
      </View>

      {/* Content */}
      <View style={st.content}>
        <Text style={[
          st.label,
          (done || active) ? st.labelActive : st.labelInactive,
        ]}>
          {step.label}
        </Text>
        <Text style={st.detail}>{step.detail}</Text>
        {active && (
          <Animated.Text entering={FadeIn.duration(300)} style={st.activeTag}>
            In progress…
          </Animated.Text>
        )}
        {done && (
          <Animated.Text entering={FadeIn.duration(300)} style={st.doneTag}>
            Complete
          </Animated.Text>
        )}
      </View>
    </Animated.View>
  );
}

const st = StyleSheet.create({
  row:     { flexDirection: 'row', gap: 14, minHeight: 52 },
  timeline:{ alignItems: 'center', width: scale(22) },
  mark:    { width: scale(22), height: scale(22), borderRadius: scale(11), borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.parchment, alignItems: 'center', justifyContent: 'center', zIndex: 1 },
  markDone:       { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  markActive:     { borderColor: COLORS.sage, borderWidth: 2, backgroundColor: 'rgba(58,95,82,0.08)' },
  markCheck:      { width: 9, height: 9, borderRadius: 5, backgroundColor: '#fff' },
  markActiveDot:  { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.sage },
  connector:      { flex: 1, width: 1.5, backgroundColor: COLORS.border, marginVertical: 2 },
  connectorDone:  { backgroundColor: COLORS.ink },
  content:  { flex: 1, paddingTop: 2, paddingBottom: 16, gap: 2 },
  label:        { ...TYPE.titleMed },
  labelActive:  { color: COLORS.ink },
  labelInactive:{ color: COLORS.textFaint },
  detail:       { ...TYPE.micro, color: COLORS.textFaint },
  activeTag:    { ...TYPE.micro, color: COLORS.sage, fontWeight: '700', letterSpacing: 0.5, marginTop: 2 },
  doneTag:      { ...TYPE.micro, color: COLORS.ink, fontWeight: '700', letterSpacing: 0.5, marginTop: 2, opacity: 0.5 },
});

// ── AnalysisScreen ────────────────────────────────────────────────────────────

export default function AnalysisScreen() {
  const store          = useAppStore();
  const isAnalysing    = store.isAnalysing;
  const analysisStep   = store.analysisStep;
  const currentSession = store.currentSession;

  const STEPS = useMemo<Step[]>(() => {
    const base: Step[] = [
      { label: 'Transcribing & translating',  detail: 'Whisper · IndicTrans' },
      { label: 'Extracting symptoms',          detail: 'Gemini NLP · spaCy NER' },
      { label: 'Running diagnosis model',      detail: '132-disease XGBoost' },
    ];
    if (store.audioUri) base.push({ label: 'Analysing respiratory audio', detail: 'Audio model · Cough detection' });
    if (store.imageUri) base.push({ label: 'Analysing medical image',     detail: 'Vision model · Pathology detection' });
    if (store.audioUri && store.imageUri) base.push({ label: 'Fusing multimodal signals', detail: 'Confidence-weighted voting' });
    base.push({ label: 'Locating nearby care', detail: 'PHC · CHC · District hospital' });
    return base;
  }, [store.audioUri, store.imageUri]);

  useEffect(() => {
    if (!isAnalysing && currentSession) {
      router.replace('/result');
    }
  }, [isAnalysing, currentSession]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>

        {/* Header */}
        <Animated.View entering={FadeIn.duration(500)} style={styles.header}>
          <Text style={styles.wordmark}>VAIDYA</Text>
          <Text style={styles.subtitle}>Analysing your symptoms</Text>
        </Animated.View>

        {/* Central animation */}
        <Animated.View entering={FadeIn.duration(600).delay(100)} style={styles.orbWrap}>
          <CentralOrb />
        </Animated.View>

        {/* Step list */}
        <Animated.View entering={FadeInDown.duration(500).delay(200)} style={styles.steps}>
          {STEPS.map((step, i) => (
            <StepRow
              key={step.label}
              step={step}
              active={i === analysisStep}
              done={i < analysisStep}
              index={i}
              isLast={i === STEPS.length - 1}
            />
          ))}
        </Animated.View>

        {/* Disclaimer */}
        <Animated.Text entering={FadeIn.duration(600).delay(700)} style={styles.disclaimer}>
          AI-assisted assessment — always verify with a licensed doctor
        </Animated.Text>

      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: COLORS.parchment },
  container: { flex: 1, paddingHorizontal: 32, paddingVertical: 24, justifyContent: 'center', gap: 36 },

  header:   { gap: 6 },
  wordmark: { ...TYPE.micro, color: COLORS.textMuted, letterSpacing: 4, fontWeight: '700' },
  subtitle: { fontSize: mScale(28), fontWeight: '700', letterSpacing: -0.7, color: COLORS.ink, lineHeight: mScale(34) },

  orbWrap: { alignItems: 'center', justifyContent: 'center' },

  steps: { gap: 0 },

  disclaimer: { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', letterSpacing: 0.3 },
});
