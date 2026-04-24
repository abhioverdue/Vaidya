/**
 * Vaidya — Settings screen  (v3 · Auth-aware, every button functional)
 * Sections: Profile · Language · AI Model · Data & Privacy · Account · About
 */

import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet, Alert, Linking,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { COLORS, LANGUAGES, TYPE, RADIUS } from '@/constants';

// ── Section ───────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={sec.wrap}>
      <Text style={sec.title}>{title}</Text>
      <View style={sec.card}>{children}</View>
    </View>
  );
}

const sec = StyleSheet.create({
  wrap:  { marginBottom: 24 },
  title: { ...TYPE.micro, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8, paddingHorizontal: 4, fontWeight: '700' },
  card:  { backgroundColor: COLORS.surface, borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.border, overflow: 'hidden', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 6, elevation: 2 },
});

// ── Row ───────────────────────────────────────────────────────────────────────

function Row({
  icon, label, sub, onPress, rightEl, isLast = false, destructive = false,
}: {
  icon: string; label: string; sub?: string;
  onPress?: () => void; rightEl?: React.ReactNode;
  isLast?: boolean; destructive?: boolean;
}) {
  return (
    <TouchableOpacity
      style={[row.row, !isLast && row.rowBorder]}
      onPress={onPress}
      activeOpacity={onPress ? 0.7 : 1}
    >
      <View style={[row.iconWrap, destructive && row.iconWrapDestructive]}>
        <Text style={row.icon}>{icon}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[row.label, destructive && row.labelDestructive]}>{label}</Text>
        {sub && <Text style={row.sub}>{sub}</Text>}
      </View>
      {rightEl ?? (onPress ? <Text style={row.chevron}>›</Text> : null)}
    </TouchableOpacity>
  );
}

const row = StyleSheet.create({
  row:              { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  rowBorder:        { borderBottomWidth: 1, borderBottomColor: COLORS.border },
  iconWrap:         { width: 36, height: 36, borderRadius: 10, backgroundColor: COLORS.primaryGhost, alignItems: 'center', justifyContent: 'center' },
  iconWrapDestructive: { backgroundColor: 'rgba(194,59,34,0.08)' },
  icon:             { fontSize: 17 },
  label:            { ...TYPE.titleMed, color: COLORS.text },
  labelDestructive: { color: COLORS.crimson },
  sub:              { ...TYPE.micro, color: COLORS.textMuted, marginTop: 2 },
  chevron:          { fontSize: 20, color: COLORS.textDisabled },
});

// ── ProfileCard ───────────────────────────────────────────────────────────────

function ProfileCard({ name, phone }: { name: string; phone: string }) {
  const initial = name ? name.charAt(0).toUpperCase() : '?';
  const maskedPhone = phone.length >= 4
    ? `+91 ••••${phone.slice(-4)}`
    : phone;

  return (
    <View style={pc.card}>
      <View style={pc.avatar}>
        <Text style={pc.avatarText}>{initial}</Text>
      </View>
      <View style={pc.info}>
        <Text style={pc.name}>{name || 'Your Name'}</Text>
        <Text style={pc.phone}>{maskedPhone || '+91 ••••••••••'}</Text>
      </View>
      <View style={pc.badge}>
        <View style={pc.badgeDot} />
        <Text style={pc.badgeText}>Verified</Text>
      </View>
    </View>
  );
}

const pc = StyleSheet.create({
  card:       { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.surface, borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.border, padding: 16, gap: 14, marginBottom: 8, shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 6, elevation: 2 },
  avatar:     { width: 52, height: 52, borderRadius: 26, backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 22, fontWeight: '800', color: COLORS.parchment },
  info:       { flex: 1, gap: 3 },
  name:       { ...TYPE.headlineMed, color: COLORS.ink },
  phone:      { ...TYPE.bodySmall, color: COLORS.textMuted },
  badge:      { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: COLORS.sageGhost, borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)' },
  badgeDot:   { width: 5, height: 5, borderRadius: 3, backgroundColor: COLORS.sage },
  badgeText:  { ...TYPE.micro, color: COLORS.sage, fontWeight: '700' },
});

// ── SettingsScreen ────────────────────────────────────────────────────────────

export default function SettingsScreen() {
  const store    = useAppStore();
  const language = store.language;
  const user     = store.user;

  function confirmClear() {
    Alert.alert('Clear history?', 'All triage sessions will be deleted from this device.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear', style: 'destructive', onPress: () => { store.clearHistory(); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); } },
    ]);
  }

  function confirmLogout() {
    Alert.alert(
      'Sign out?',
      'You will need to sign in again to use Vaidya.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign out',
          style: 'destructive',
          onPress: async () => {
            await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
            await store.logout();
            router.replace('/login');
          },
        },
      ],
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={styles.backBtn}
          accessibilityLabel="Go back"
        >
          <View style={styles.backCircle}>
            <Text style={styles.backText}>←</Text>
          </View>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={styles.headerRight} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>

        {/* Profile card */}
        <Animated.View entering={FadeInDown.duration(400)}>
          <Text style={styles.sectionLabel}>PROFILE</Text>
          <ProfileCard name={user?.name ?? ''} phone={user?.phone ?? ''} />
        </Animated.View>

        {/* Language */}
        <Animated.View entering={FadeInDown.duration(400).delay(60)}>
          <Section title="Language">
            {LANGUAGES.map((lang, i) => (
              <Row
                key={lang.code}
                icon={lang.flag || (lang.code === 'en' ? '🇬🇧' : lang.code === 'hi' ? '🇮🇳' : '🇮🇳')}
                label={lang.nativeName}
                sub={lang.name}
                onPress={() => { store.setLanguage(lang.code); Haptics.selectionAsync(); }}
                isLast={i === LANGUAGES.length - 1}
                rightEl={
                  language === lang.code
                    ? <View style={styles.selectedDot} />
                    : null
                }
              />
            ))}
          </Section>
        </Animated.View>

        {/* AI Model status */}
        <Animated.View entering={FadeInDown.duration(400).delay(120)}>
          <Section title="AI Model">
            <Row
              icon="✨"
              label="Gemini AI (Online)"
              sub={store.isOnline ? 'Active · gemini-1.5-flash' : 'Unavailable — offline'}
              isLast={false}
              onPress={() => {
                Haptics.selectionAsync();
                Alert.alert(
                  'Gemini AI Model',
                  `Model: gemini-1.5-flash\nProvider: Google DeepMind\nStatus: ${store.isOnline ? 'Connected' : 'Unavailable'}\n\nThis model powers online symptom analysis with multi-language support and reasoning.`,
                );
              }}
              rightEl={
                <View style={[styles.statusPill, { backgroundColor: store.isOnline ? COLORS.successLight : COLORS.errorLight }]}>
                  <Text style={[styles.statusPillText, { color: store.isOnline ? COLORS.success : COLORS.error }]}>
                    {store.isOnline ? 'Online' : 'Offline'}
                  </Text>
                </View>
              }
            />
            <Row
              icon="📱"
              label="TFLite Offline Model"
              sub="On-device · XGBoost distilled · 132 diseases"
              isLast
              onPress={() => {
                Haptics.selectionAsync();
                Alert.alert(
                  'Offline AI Model',
                  'Model: XGBoost distilled to TFLite\nConditions: 132 diseases\nSize: ~4 MB\nStatus: Ready\n\nRuns fully on-device with no internet required. Used as fallback when offline.',
                );
              }}
              rightEl={
                <View style={[styles.statusPill, { backgroundColor: COLORS.successLight }]}>
                  <Text style={[styles.statusPillText, { color: COLORS.success }]}>Ready</Text>
                </View>
              }
            />
          </Section>
        </Animated.View>

        {/* Data & Privacy */}
        <Animated.View entering={FadeInDown.duration(400).delay(180)}>
          <Section title="Data & Privacy">
            <Row
              icon="🗑"
              label="Clear session history"
              sub={`${store.sessionHistory.length} session${store.sessionHistory.length !== 1 ? 's' : ''} stored locally`}
              onPress={confirmClear}
              isLast={false}
            />
            <Row
              icon="🔒"
              label="All data stays on device"
              sub="No user data is uploaded to any server"
              isLast
              onPress={() => {
                Haptics.selectionAsync();
                Alert.alert(
                  'Privacy Policy',
                  'Vaidya stores all session data locally on your device only.\n\n• No symptoms, photos, or audio are uploaded\n• No account data is sold or shared\n• Anonymised, aggregated patterns may be used for public health research with your consent\n• You can clear all data at any time',
                );
              }}
            />
          </Section>
        </Animated.View>

        {/* Account */}
        <Animated.View entering={FadeInDown.duration(400).delay(240)}>
          <Section title="Account">
            <Row
              icon="🔑"
              label="Change password"
              sub="Update your account password"
              onPress={() => {
                Haptics.selectionAsync();
                // Reset pending state so phase 1 shows (send OTP to phone)
                store.setPendingReg(null);
                router.push('/reset-password');
              }}
              isLast={false}
            />
            <Row
              icon="📞"
              label="Update mobile number"
              sub={user?.phone ? `+91 ${user.phone}` : 'Not set'}
              onPress={() => {
                Haptics.selectionAsync();
                Alert.alert('Update mobile', 'Contact support to update your registered mobile number.');
              }}
              isLast={false}
            />
            <Row
              icon="🚪"
              label="Sign out"
              sub="Sign out of this device"
              onPress={confirmLogout}
              isLast
              destructive
            />
          </Section>
        </Animated.View>

        {/* About */}
        <Animated.View entering={FadeInDown.duration(400).delay(300)}>
          <Section title="About">
            <Row
              icon="ℹ️"
              label="Vaidya v1.0.0"
              sub="AI health triage for rural India"
              isLast={false}
              onPress={() => {
                Haptics.selectionAsync();
                Alert.alert(
                  'About Vaidya v1.0.0',
                  'Vaidya is an AI-powered health triage tool built for ASHA workers and rural communities across India.\n\nStack: React Native · Expo · Gemini 1.5 Flash · XGBoost · TFLite\n\nBuilt for Google Solutions Challenge.',
                );
              }}
            />
            <Row
              icon="⚠️"
              label="Medical disclaimer"
              sub="Not a substitute for professional diagnosis"
              onPress={() =>
                Alert.alert(
                  'Medical Disclaimer',
                  'Vaidya is an AI-assisted triage tool. It does not replace professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider.',
                )
              }
              isLast={false}
            />
            <Row
              icon="🩺"
              label="eSanjeevani teleconsult"
              sub="Free teleconsult with govt doctors"
              onPress={() => {
                Haptics.selectionAsync();
                Linking.openURL('https://esanjeevani.mohfw.gov.in/#/');
              }}
              isLast={false}
            />
            <Row
              icon="🆘"
              label="Emergency · Dial 108"
              sub="National ambulance service"
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
                Linking.openURL('tel:108');
              }}
              isLast
              destructive
            />
          </Section>
        </Animated.View>

        <Text style={styles.footer}>
          Vaidya · Gemini 1.5 Flash · XGBoost · TFLite{'\n'}
          Built for ASHA workers & rural communities of India
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 14,
    backgroundColor: COLORS.surface, borderBottomWidth: 1, borderBottomColor: COLORS.border,
  },
  backBtn:    { width: 40 },
  backCircle: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.background, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backText:   { fontSize: 18, color: COLORS.primary, fontWeight: '700', marginTop: -1 },
  headerTitle:{ ...TYPE.headlineMed, color: COLORS.text },
  headerRight:{ width: 40 },

  scroll:  { padding: 20, paddingBottom: 52 },

  sectionLabel: { ...TYPE.micro, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8, paddingHorizontal: 4, fontWeight: '700' },

  selectedDot:   { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },
  statusPill:    { borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 4 },
  statusPillText:{ fontSize: 11, fontWeight: '700' },

  footer: { ...TYPE.micro, color: COLORS.textDisabled, textAlign: 'center', lineHeight: 18, marginTop: 8 },
});
