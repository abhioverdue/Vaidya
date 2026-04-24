/**
 * Vaidya — Language Selection  (v3 · Senior Apple Designer Redesign)
 * Animated entry, scale-press cards, elegant wordmark, floating background accents.
 */

import { View, Text, TouchableOpacity, StyleSheet, Pressable } from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeInDown, FadeInUp,
  useSharedValue, useAnimatedStyle,
  withSpring, withRepeat, withTiming, withSequence, withDelay,
  Easing,
} from 'react-native-reanimated';
import { useCallback, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Haptics from 'expo-haptics';
import { useAppStore } from '@/store';
import { COLORS, STORAGE_KEYS, TYPE, RADIUS } from '@/constants';
import type { Language } from '@/types';

// ── Language data ─────────────────────────────────────────────────────────────

const LANGS: Array<{
  code: Language;
  label: string;
  sub: string;
  script: string;
  accent: string;
}> = [
  { code: 'en', label: 'English',  sub: 'Continue in English',      script: 'Aa', accent: COLORS.sage },
  { code: 'hi', label: 'हिन्दी',   sub: 'हिन्दी में जारी रखें',       script: 'अ',  accent: COLORS.gold },
  { code: 'ta', label: 'தமிழ்',    sub: 'தமிழில் தொடரவும்',          script: 'த',  accent: COLORS.crimson },
];

// ── Floating accent orb ───────────────────────────────────────────────────────

function FloatingOrb({ size, top, left, color, delay }: {
  size: number; top: number; left: number; color: string; delay: number;
}) {
  const y = useSharedValue(0);
  useEffect(() => {
    y.value = withDelay(delay, withRepeat(
      withSequence(
        withTiming(-12, { duration: 2800, easing: Easing.inOut(Easing.sin) }),
        withTiming(0,   { duration: 2800, easing: Easing.inOut(Easing.sin) }),
      ),
      -1, false,
    ));
  }, []);
  const style = useAnimatedStyle(() => ({
    position: 'absolute',
    top,
    left,
    width: size,
    height: size,
    borderRadius: size / 2,
    backgroundColor: color,
    opacity: 0.07,
    transform: [{ translateY: y.value }],
  }));
  return <Animated.View style={style} />;
}

// ── LanguageCard ──────────────────────────────────────────────────────────────

function LanguageCard({ lang, index, onPress }: {
  lang: typeof LANGS[0]; index: number; onPress: () => void;
}) {
  const scale = useSharedValue(1);
  const onPressIn  = useCallback(() => { scale.value = withSpring(0.96, { damping: 22, stiffness: 350 }); }, []);
  const onPressOut = useCallback(() => { scale.value = withSpring(1,    { damping: 16, stiffness: 280 }); }, []);
  const animStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  return (
    <Animated.View
      style={animStyle}
      entering={FadeInDown.duration(500).delay(index * 100 + 300)}
    >
      <Pressable
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        onPress={async () => {
          await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
          onPress();
        }}
        style={s.card}
      >
        {/* Script badge */}
        <View style={[s.scriptBadge, { backgroundColor: `${lang.accent}14`, borderColor: `${lang.accent}28` }]}>
          <Text style={[s.scriptText, { color: lang.accent }]}>{lang.script}</Text>
        </View>

        {/* Text */}
        <View style={s.cardText}>
          <Text style={s.cardLang}>{lang.label}</Text>
          <Text style={s.cardSub}>{lang.sub}</Text>
        </View>

        {/* Arrow */}
        <View style={[s.cardArrow, { backgroundColor: `${lang.accent}12` }]}>
          <Text style={[s.arrowText, { color: lang.accent }]}>›</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

// ── LanguageSelectScreen ──────────────────────────────────────────────────────

export default function LanguageSelectScreen() {
  const setLanguage = useAppStore((s) => s.setLanguage);

  async function handleSelect(lang: Language) {
    await setLanguage(lang);
    router.replace('/consent');
  }

  return (
    <SafeAreaView style={s.safe}>

      {/* Background floating orbs */}
      <FloatingOrb size={180} top={-40}  left={-60}  color={COLORS.sage}    delay={0}    />
      <FloatingOrb size={140} top={320}  left={220}  color={COLORS.gold}    delay={600}  />
      <FloatingOrb size={100} top={580}  left={-20}  color={COLORS.crimson} delay={1200} />

      <View style={s.container}>

        {/* Wordmark */}
        <Animated.View entering={FadeInUp.duration(700)} style={s.topSection}>
          <View style={s.logoRow}>
            <View style={s.logoMark}>
              <Text style={s.logoMarkText}>V</Text>
            </View>
            <View style={s.wordmarkBlock}>
              <Text style={s.wordmark}>VAIDYA</Text>
              <Text style={s.wordmarkSub}>AI Health Triage</Text>
            </View>
          </View>

          <View style={s.dividerRow}>
            <View style={s.dividerLine} />
            <Text style={s.dividerText}>भारत · இந்தியா · India</Text>
            <View style={s.dividerLine} />
          </View>

          <Text style={s.heroLabel}>Choose your language</Text>
          <Text style={s.heroSub}>
            Available in 3 languages.{'\n'}You can change this anytime in settings.
          </Text>
        </Animated.View>

        {/* Language cards */}
        <View style={s.cards}>
          {LANGS.map((lang, i) => (
            <LanguageCard
              key={lang.code}
              lang={lang}
              index={i}
              onPress={() => handleSelect(lang.code)}
            />
          ))}
        </View>

        {/* Trust footer */}
        <Animated.View entering={FadeInDown.duration(500).delay(700)} style={s.footer}>
          <View style={s.trustRow}>
            <View style={s.trustChip}>
              <View style={s.trustDot} />
              <Text style={s.trustText}>Free</Text>
            </View>
            <View style={s.trustChip}>
              <View style={[s.trustDot, { backgroundColor: COLORS.sage }]} />
              <Text style={s.trustText}>Offline ready</Text>
            </View>
            <View style={s.trustChip}>
              <View style={[s.trustDot, { backgroundColor: COLORS.gold }]} />
              <Text style={s.trustText}>No data sold</Text>
            </View>
          </View>
        </Animated.View>

      </View>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:       { flex: 1, backgroundColor: COLORS.parchment },
  container:  { flex: 1, paddingHorizontal: 28, justifyContent: 'center', gap: 36 },

  // Top section
  topSection: { gap: 16 },
  logoRow:    { flexDirection: 'row', alignItems: 'center', gap: 14 },
  logoMark:   { width: 48, height: 48, borderRadius: 14, backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 8, elevation: 6 },
  logoMarkText:{ fontSize: 22, fontWeight: '800', color: COLORS.parchment, letterSpacing: 1 },
  wordmarkBlock:{ gap: 2 },
  wordmark:   { fontSize: 18, fontWeight: '800', letterSpacing: 4, color: COLORS.ink },
  wordmarkSub:{ ...TYPE.micro, color: COLORS.textMuted, letterSpacing: 1 },

  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  dividerLine:{ flex: 1, height: 1, backgroundColor: COLORS.border },
  dividerText:{ ...TYPE.micro, color: COLORS.textFaint, letterSpacing: 0.5 },

  heroLabel: { fontSize: 26, fontWeight: '700', letterSpacing: -0.5, color: COLORS.ink, lineHeight: 32 },
  heroSub:   { ...TYPE.bodySmall, color: COLORS.textMuted, lineHeight: 21 },

  // Cards
  cards: { gap: 12 },
  card:  {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingVertical: 18,
    paddingHorizontal: 18,
    gap: 16,
    shadowColor: COLORS.ink,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },

  scriptBadge: { width: 52, height: 52, borderRadius: RADIUS.lg, alignItems: 'center', justifyContent: 'center', borderWidth: 1, flexShrink: 0 },
  scriptText:  { fontSize: 22, fontWeight: '800' },
  cardText:    { flex: 1, gap: 3 },
  cardLang:    { ...TYPE.headlineMed, color: COLORS.ink },
  cardSub:     { ...TYPE.bodySmall, color: COLORS.textMuted },
  cardArrow:   { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  arrowText:   { fontSize: 22, fontWeight: '300', marginTop: -1 },

  // Footer
  footer:   { alignItems: 'center' },
  trustRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap', justifyContent: 'center' },
  trustChip:{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: COLORS.surface, borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: COLORS.border },
  trustDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: COLORS.textFaint },
  trustText:{ ...TYPE.micro, color: COLORS.textSub, fontWeight: '600' },
});
