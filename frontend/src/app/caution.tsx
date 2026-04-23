/**
 * Vaidya — Caution / Advisory screen
 * Shown once after language selection. Clinical, respectful, clear.
 * No alarm — just honest transparency about what this tool is and isn't.
 */

import { View, Text, TouchableOpacity, ScrollView, StyleSheet, Linking } from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { COLORS, TYPE, RADIUS, STORAGE_KEYS } from '@/constants';

const POINTS = [
  {
    heading: 'Assistive, not authoritative',
    body: 'Vaidya uses AI to suggest possible conditions based on your symptoms. It does not replace a licensed physician\'s examination, diagnosis, or prescription.',
  },
  {
    heading: 'Always verify with a doctor',
    body: 'Any condition flagged here should be confirmed by a qualified healthcare provider before you act on it. If symptoms are severe, seek immediate medical attention.',
  },
  {
    heading: 'Your data stays private',
    body: 'No personally identifiable information is stored or sold. Anonymised patterns may be used to improve public health monitoring, with your consent.',
  },
  {
    heading: 'Emergency services',
    body: 'In a medical emergency, call 108 immediately. Do not rely on this application when urgent professional care is required.',
  },
];

export default function CautionScreen() {
  async function handleAccept() {
    await AsyncStorage.setItem(STORAGE_KEYS.CAUTION_SEEN, '1');
    router.replace('/login' as any);
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Header */}
        <Animated.View entering={FadeInUp.duration(500)} style={s.header}>
          <View style={s.headerRule} />
          <View style={s.headerTextWrap}>
            <Text style={s.headerLabel}>BEFORE YOU BEGIN</Text>
            <Text style={s.headerTitle}>A note on how{'\n'}to use Vaidya</Text>
          </View>
        </Animated.View>

        {/* Points */}
        <View style={s.points}>
          {POINTS.map((pt, i) => (
            <Animated.View
              key={pt.heading}
              entering={FadeInDown.duration(500).delay(i * 80 + 200)}
              style={s.point}
            >
              <View style={s.pointNum}>
                <Text style={s.pointNumText}>{String(i + 1).padStart(2, '0')}</Text>
              </View>
              <View style={s.pointBody}>
                <Text style={s.pointHeading}>{pt.heading}</Text>
                <Text style={s.pointText}>{pt.body}</Text>
              </View>
            </Animated.View>
          ))}
        </View>

        {/* Divider */}
        <Animated.View entering={FadeInDown.duration(400).delay(550)} style={s.divider} />

        {/* Consent note */}
        <Animated.View entering={FadeInDown.duration(400).delay(600)} style={s.consentNote}>
          <Text style={s.consentText}>
            By continuing, you acknowledge that this tool provides AI-assisted health information only, and does not constitute medical advice.
          </Text>
        </Animated.View>

        {/* CTA */}
        <Animated.View entering={FadeInDown.duration(400).delay(700)} style={s.ctaWrap}>
          <TouchableOpacity style={s.ctaBtn} onPress={handleAccept} activeOpacity={0.88}>
            <Text style={s.ctaBtnText}>I understand — continue</Text>
          </TouchableOpacity>
        </Animated.View>

        {/* Emergency note at base */}
        <Animated.View entering={FadeInDown.duration(400).delay(800)} style={s.emergencyNote}>
          <View style={s.emergencyLine} />
          <TouchableOpacity onPress={() => Linking.openURL('tel:108')} activeOpacity={0.7}>
            <Text style={s.emergencyText}>Medical emergency? Call 108 now.</Text>
          </TouchableOpacity>
        </Animated.View>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { paddingHorizontal: 28, paddingBottom: 52, paddingTop: 20 },

  header:       { marginBottom: 36 },
  headerRule:   { height: 3, width: 36, backgroundColor: COLORS.crimson, marginBottom: 20, borderRadius: 2 },
  headerTextWrap: { gap: 8 },
  headerLabel:  {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 2,
    color: COLORS.crimson,
  },
  headerTitle:  {
    fontSize: 32,
    fontWeight: '700',
    letterSpacing: -0.8,
    lineHeight: 38,
    color: COLORS.ink,
  },

  points:       { gap: 28, marginBottom: 36 },
  point:        { flexDirection: 'row', gap: 16, alignItems: 'flex-start' },
  pointNum:     {
    width: 36,
    height: 36,
    borderRadius: RADIUS.sm,
    backgroundColor: COLORS.inkGhost,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginTop: 2,
  },
  pointNumText: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
    color: COLORS.textMuted,
  },
  pointBody:    { flex: 1, gap: 5 },
  pointHeading: { ...TYPE.titleMed, color: COLORS.ink },
  pointText:    { ...TYPE.bodyMed, color: COLORS.textSub, lineHeight: 22 },

  divider:      { height: 1, backgroundColor: COLORS.border, marginBottom: 24 },

  consentNote:  {
    backgroundColor: COLORS.parchmentWarm,
    borderRadius: RADIUS.md,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: 24,
  },
  consentText:  { ...TYPE.bodySmall, color: COLORS.textSub, lineHeight: 20, textAlign: 'center' },

  ctaWrap: { marginBottom: 24 },
  ctaBtn: {
    backgroundColor: COLORS.ink,
    borderRadius: RADIUS.lg,
    paddingVertical: 20,
    alignItems: 'center',
  },
  ctaBtnText: { ...TYPE.titleLarge, color: COLORS.textInverse, letterSpacing: 0.2 },

  emergencyNote: {
    alignItems: 'center',
    gap: 10,
  },
  emergencyLine: { height: 1, width: 32, backgroundColor: COLORS.crimson, borderRadius: 1 },
  emergencyText: { ...TYPE.micro, color: COLORS.crimson, letterSpacing: 0.8, fontWeight: '700' },
});
