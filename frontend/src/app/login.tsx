import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';
import { useState } from 'react';
import * as Haptics from 'expo-haptics';
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
} from 'firebase/auth';

import { useTranslation } from 'react-i18next';
import { getFirebaseAuth, isFirebaseConfigured } from '@/services/firebase';
import { useAppStore }     from '@/store';
import { COLORS, TYPE, RADIUS } from '@/constants';

export default function LoginScreen() {
  const { t } = useTranslation();
  const { setAuth } = useAppStore();

  const [mode,     setMode]     = useState<'signin' | 'signup'>('signin');
  const [name,     setName]     = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  const canSubmit = email.trim().length > 0 && password.length >= 6
    && (mode === 'signin' || name.trim().length >= 2);

  async function handleSubmit() {
    if (!canSubmit) return;
    setError('');
    setLoading(true);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    try {
      if (!isFirebaseConfigured()) {
        // Firebase keys not baked in (dev / internal build) — allow demo login
        await setAuth(
          { id: 'demo-' + Date.now(), name: name.trim() || email.trim() || 'Guest', phone: '' },
          'demo-token',
        );
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        router.replace('/');
        return;
      }
      const auth = getFirebaseAuth();
      let userCred;

      if (mode === 'signup') {
        userCred = await createUserWithEmailAndPassword(auth, email.trim(), password);
        try { await updateProfile(userCred.user, { displayName: name.trim() }); } catch {}
      } else {
        userCred = await signInWithEmailAndPassword(auth, email.trim(), password);
      }

      const token = await userCred.user.getIdToken();
      await setAuth(
        {
          id:    userCred.user.uid,
          name:  userCred.user.displayName ?? name.trim() ?? email.trim(),
          phone: '',
        },
        token,
      );

      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace('/');
    } catch (e: any) {
      const code: string = e?.code ?? '';

      // Network unreachable → show error, do not silently bypass login
      if (code === 'auth/network-request-failed') {
        setError(t('auth.err_network'));
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        return;
      }

      const friendly: Record<string, string> = {
        'auth/invalid-credential':       t('auth.err_invalid_credential'),
        'auth/wrong-password':           t('auth.err_wrong_password'),
        'auth/user-not-found':           t('auth.err_user_not_found'),
        'auth/email-already-in-use':     t('auth.err_email_in_use'),
        'auth/weak-password':            t('auth.err_weak_password'),
        'auth/invalid-email':            t('auth.err_invalid_email'),
        'auth/too-many-requests':        t('auth.err_too_many_requests'),
        'auth/user-disabled':            t('auth.err_user_disabled'),
        'auth/operation-not-allowed':    t('auth.err_op_not_allowed'),
      };
      setError(friendly[code] ?? t('common.error'));
      setLoading(false);
    }
  }

  function switchMode() {
    setError('');
    setMode(m => m === 'signin' ? 'signup' : 'signin');
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={s.root}>

          {/* ── Brand ── */}
          <Animated.View entering={FadeInDown.duration(460)} style={s.brand}>
            <View style={s.logoRow}>
              <View style={s.dot1} />
              <View style={s.dot2} />
            </View>
            <Text style={s.wordmark}>{t('common.app_name').toUpperCase()}</Text>
            <Text style={s.tagline}>{t('auth.tagline')}</Text>
          </Animated.View>

          {/* ── Feature chips ── */}
          <Animated.View entering={FadeInDown.duration(420).delay(80)} style={s.chips}>
            {[t('auth.conditions_count'), t('auth.gemini_ai'), t('auth.offline_ready'), t('auth.three_languages')].map((c) => (
              <View key={c} style={s.chip}>
                <View style={s.chipDot} />
                <Text style={s.chipText}>{c}</Text>
              </View>
            ))}
          </Animated.View>

          {/* ── Card ── */}
          <Animated.View entering={FadeInDown.duration(420).delay(160)} style={s.card}>

            {/* Mode toggle */}
            <View style={s.modeRow}>
              <TouchableOpacity
                style={[s.modeTab, mode === 'signin' && s.modeTabActive]}
                onPress={() => mode !== 'signin' && switchMode()}
              >
                <Text style={[s.modeTabText, mode === 'signin' && s.modeTabTextActive]}>{t('auth.sign_in')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.modeTab, mode === 'signup' && s.modeTabActive]}
                onPress={() => mode !== 'signup' && switchMode()}
              >
                <Text style={[s.modeTabText, mode === 'signup' && s.modeTabTextActive]}>{t('auth.create_account')}</Text>
              </TouchableOpacity>
            </View>

            <Text style={s.cardSub}>{t('auth.data_on_device')}</Text>

            {error ? (
              <View style={s.errorBox}>
                <Text style={s.errorText}>{error}</Text>
              </View>
            ) : null}

            {mode === 'signup' && (
              <View style={s.field}>
                <Text style={s.label}>{t('auth.full_name')}</Text>
                <TextInput
                  style={s.input}
                  placeholder={t('auth.name_placeholder')}
                  placeholderTextColor={COLORS.textFaint}
                  value={name}
                  onChangeText={setName}
                  autoCapitalize="words"
                  returnKeyType="next"
                />
              </View>
            )}

            <View style={s.field}>
              <Text style={s.label}>{t('auth.email')}</Text>
              <TextInput
                style={s.input}
                placeholder={t('auth.email_placeholder')}
                placeholderTextColor={COLORS.textFaint}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
              />
            </View>

            <View style={s.field}>
              <Text style={s.label}>{t('auth.password')}</Text>
              <TextInput
                style={s.input}
                placeholder={t('auth.password_placeholder')}
                placeholderTextColor={COLORS.textFaint}
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                returnKeyType="done"
                onSubmitEditing={handleSubmit}
              />
            </View>

            <TouchableOpacity
              style={[s.btn, (!canSubmit || loading) && s.btnDisabled]}
              onPress={handleSubmit}
              disabled={!canSubmit || loading}
              activeOpacity={0.88}
            >
              {loading
                ? <ActivityIndicator size="small" color={COLORS.parchment} />
                : <Text style={s.btnText}>
                    {mode === 'signin' ? t('auth.sign_in_btn') : t('auth.create_account_btn')}
                  </Text>}
            </TouchableOpacity>

            <Text style={s.hint}>{t('auth.no_data_shared')}</Text>

            <TouchableOpacity
              style={s.guestBtn}
              onPress={async () => {
                await setAuth({ id: 'demo-' + Date.now(), name: 'Guest', phone: '' }, 'demo-token');
                router.replace('/');
              }}
            >
              <Text style={s.guestText}>{t('auth.continue_guest')}</Text>
            </TouchableOpacity>
          </Animated.View>

          {/* ── Footer ── */}
          <Animated.View entering={FadeInUp.duration(380).delay(240)} style={s.footer}>
            <Text style={s.footerText}>{t('auth.footer')}</Text>
            <Text style={s.sos}>{t('auth.sos')}</Text>
          </Animated.View>

        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.parchment },
  flex: { flex: 1 },
  root: { flex: 1, paddingHorizontal: 28, justifyContent: 'center', gap: 24 },

  brand:    { alignItems: 'center', gap: 10 },
  logoRow:  { flexDirection: 'row', gap: 6, marginBottom: 4 },
  dot1:     { width: 12, height: 12, borderRadius: 6, backgroundColor: COLORS.sage },
  dot2:     { width: 8,  height: 8,  borderRadius: 4, backgroundColor: COLORS.sage, marginTop: 4, opacity: 0.45 },
  wordmark: { fontSize: 36, fontWeight: '800', letterSpacing: 6, color: COLORS.ink },
  tagline:  { ...TYPE.bodySmall, color: COLORS.textMuted, letterSpacing: 0.4 },

  chips:    { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' },
  chip:     { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.surface, borderRadius: RADIUS.pill, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: COLORS.border },
  chipDot:  { width: 5, height: 5, borderRadius: 3, backgroundColor: COLORS.sage },
  chipText: { ...TYPE.micro, color: COLORS.textSub, fontWeight: '600' },

  card:      { backgroundColor: COLORS.surface, borderRadius: RADIUS.xl, padding: 24, borderWidth: 1, borderColor: COLORS.border, gap: 14, shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.07, shadowRadius: 12, elevation: 4 },
  cardSub:   { ...TYPE.bodySmall, color: COLORS.textMuted },

  modeRow:         { flexDirection: 'row', backgroundColor: COLORS.parchment, borderRadius: RADIUS.lg, padding: 3, gap: 2 },
  modeTab:         { flex: 1, paddingVertical: 9, alignItems: 'center', borderRadius: RADIUS.md },
  modeTabActive:   { backgroundColor: COLORS.surface, shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 },
  modeTabText:     { fontSize: 13, fontWeight: '600', color: COLORS.textMuted },
  modeTabTextActive:{ color: COLORS.ink, fontWeight: '700' },

  errorBox:  { backgroundColor: 'rgba(194,59,34,0.08)', borderRadius: RADIUS.md, borderWidth: 1, borderColor: 'rgba(194,59,34,0.22)', padding: 12 },
  errorText: { ...TYPE.bodySmall, color: COLORS.crimson, lineHeight: 20 },

  field:    { gap: 6 },
  label:    { ...TYPE.micro, color: COLORS.textSub, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  input:    { backgroundColor: COLORS.parchment, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, paddingHorizontal: 14, paddingVertical: 13, fontSize: 16, color: COLORS.ink },

  btn:         { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 17, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  btnDisabled: { opacity: 0.4 },
  btnText:     { fontSize: 16, fontWeight: '700', color: COLORS.parchment, letterSpacing: 0.2 },

  hint:      { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', lineHeight: 18 },
  guestBtn:  { marginTop: 14, paddingVertical: 12, alignItems: 'center' },
  guestText: { ...TYPE.micro, color: COLORS.textSub, fontWeight: '600', letterSpacing: 0.3, textDecorationLine: 'underline' },

  footer:     { alignItems: 'center', gap: 8, paddingBottom: 8 },
  footerText: { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', lineHeight: 17, paddingHorizontal: 8 },
  sos:        { ...TYPE.micro, color: COLORS.crimson, fontWeight: '700', letterSpacing: 0.3 },
});
