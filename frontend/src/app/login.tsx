/**
 * Vaidya — Login screen
 * Mobile number (+91) + password. Spring animations, haptics, demo fallback.
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeInDown, FadeInUp,
  useSharedValue, useAnimatedStyle, withSpring, withTiming,
  interpolate, Easing,
} from 'react-native-reanimated';
import { useState, useRef, useCallback } from 'react';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { authLogin } from '@/services/auth';
import { COLORS, TYPE, RADIUS } from '@/constants';

// ── FloatingLabelInput ────────────────────────────────────────────────────────

interface FLInputProps {
  label:           string;
  value:           string;
  onChangeText:    (t: string) => void;
  keyboardType?:   any;
  secureTextEntry?: boolean;
  autoComplete?:   any;
  returnKeyType?:  any;
  onSubmitEditing?: () => void;
  maxLength?:      number;
  prefix?:         string;
  rightEl?:        React.ReactNode;
  error?:          string;
  autoFocus?:      boolean;
  inputRef?:       React.RefObject<TextInput>;
}

function FloatingLabelInput({
  label, value, onChangeText, keyboardType, secureTextEntry, autoComplete,
  returnKeyType, onSubmitEditing, maxLength, prefix, rightEl, error, autoFocus, inputRef,
}: FLInputProps) {
  const [focused, setFocused] = useState(false);
  const labelAnim = useSharedValue(value ? 1 : 0);

  const onFocus = useCallback(() => {
    setFocused(true);
    labelAnim.value = withTiming(1, { duration: 180, easing: Easing.out(Easing.quad) });
  }, []);

  const onBlur = useCallback(() => {
    setFocused(false);
    if (!value) labelAnim.value = withTiming(0, { duration: 160 });
  }, [value]);

  const labelStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: interpolate(labelAnim.value, [0, 1], [0, -22]) },
      { scale:      interpolate(labelAnim.value, [0, 1], [1, 0.82]) },
    ],
    color: interpolate(labelAnim.value, [0, 1], [0, 1]) > 0.5
      ? (focused ? COLORS.sage : COLORS.textMuted)
      : COLORS.textFaint,
  }));

  const borderColor = error ? COLORS.crimson : focused ? COLORS.sage : COLORS.border;

  return (
    <View style={fi.wrap}>
      <View style={[fi.field, { borderColor }]}>
        {prefix && <Text style={fi.prefix}>{prefix}</Text>}
        <View style={fi.inputWrap}>
          <Animated.Text style={[fi.label, labelStyle]}>{label}</Animated.Text>
          <TextInput
            ref={inputRef}
            style={fi.input}
            value={value}
            onChangeText={onChangeText}
            onFocus={onFocus}
            onBlur={onBlur}
            keyboardType={keyboardType}
            secureTextEntry={secureTextEntry}
            autoComplete={autoComplete}
            returnKeyType={returnKeyType}
            onSubmitEditing={onSubmitEditing}
            maxLength={maxLength}
            autoCapitalize="none"
            autoCorrect={false}
            autoFocus={autoFocus}
          />
        </View>
        {rightEl && <View style={fi.rightEl}>{rightEl}</View>}
      </View>
      {error ? <Text style={fi.error}>{error}</Text> : null}
    </View>
  );
}

const fi = StyleSheet.create({
  wrap:     { marginBottom: 16 },
  field:    { flexDirection: 'row', alignItems: 'center', borderWidth: 1.5, borderRadius: RADIUS.lg, backgroundColor: COLORS.surface, paddingHorizontal: 16, minHeight: 58 },
  prefix:   { ...TYPE.bodyMed, color: COLORS.textSub, marginRight: 6, fontWeight: '600', paddingTop: 14 },
  inputWrap:{ flex: 1, position: 'relative', justifyContent: 'center', paddingTop: 14 },
  label:    { position: 'absolute', ...TYPE.bodyMed, color: COLORS.textFaint, transformOrigin: 'left center' as any, top: 18 },
  input:    { ...TYPE.bodyMed, color: COLORS.ink, paddingVertical: 4, paddingBottom: 8 },
  rightEl:  { marginLeft: 8 },
  error:    { ...TYPE.micro, color: COLORS.crimson, marginTop: 4, marginLeft: 4 },
});

// ── LoginScreen ───────────────────────────────────────────────────────────────

export default function LoginScreen() {
  const setAuth = useAppStore((s) => s.setAuth);

  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [errors,   setErrors]   = useState<{ email?: string; password?: string; general?: string }>({});

  const passwordRef = useRef<TextInput>(null);

  const btnScale = useSharedValue(1);
  const btnStyle = useAnimatedStyle(() => ({ transform: [{ scale: btnScale.value }] }));

  function validate(): boolean {
    const e: typeof errors = {};
    if (!email.trim())                                          e.email    = 'Enter your email address';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) e.email   = 'Enter a valid email address';
    if (!password)                                              e.password = 'Enter your password';
    else if (password.length < 6)                               e.password = 'Password must be at least 6 characters';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleLogin() {
    if (!validate()) { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error); return; }
    setLoading(true);
    setErrors({});
    try {
      const res = await authLogin(email.trim(), password);
      await setAuth(res.user, res.access_token);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace('/');
    } catch (err: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const msg = err?.response?.data?.detail ?? err?.message ?? 'Login failed. Please try again.';
      setErrors({ general: String(msg) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={s.scroll}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Logo */}
          <Animated.View entering={FadeInUp.duration(600)} style={s.logoWrap}>
            <View style={s.logoMark}>
              <Text style={s.logoMarkText}>V</Text>
            </View>
            <Text style={s.wordmark}>VAIDYA</Text>
            <Text style={s.tagline}>AI Health Triage for India</Text>
          </Animated.View>

          {/* Heading */}
          <Animated.View entering={FadeInDown.duration(440).delay(100)} style={s.headingWrap}>
            <Text style={s.heading}>Welcome back</Text>
            <Text style={s.subheading}>Sign in to continue your health journey</Text>
          </Animated.View>

          {/* Form */}
          <Animated.View entering={FadeInDown.duration(440).delay(180)} style={s.form}>
            {errors.general && (
              <View style={s.errorBanner}>
                <Text style={s.errorBannerText}>{errors.general}</Text>
              </View>
            )}

            <FloatingLabelInput
              label="Email address"
              value={email}
              onChangeText={(t) => { setEmail(t.trim()); setErrors((e) => ({ ...e, email: undefined })); }}
              keyboardType="email-address"
              autoComplete="email"
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              error={errors.email}
              autoFocus
            />

            <FloatingLabelInput
              label="Password"
              value={password}
              onChangeText={(t) => { setPassword(t); setErrors((e) => ({ ...e, password: undefined })); }}
              secureTextEntry={!showPass}
              autoComplete="password"
              returnKeyType="done"
              onSubmitEditing={handleLogin}
              inputRef={passwordRef}
              error={errors.password}
              rightEl={
                <TouchableOpacity onPress={() => setShowPass((v) => !v)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Text style={s.showHide}>{showPass ? 'Hide' : 'Show'}</Text>
                </TouchableOpacity>
              }
            />

            <TouchableOpacity
              style={s.forgotWrap}
              onPress={() => router.push('/reset-password')}
            >
              <Text style={s.forgotText}>Forgot password?</Text>
            </TouchableOpacity>

            {/* Sign in button */}
            <Animated.View style={btnStyle}>
              <TouchableOpacity
                style={[s.btn, loading && s.btnLoading]}
                onPress={handleLogin}
                onPressIn={() => { btnScale.value = withSpring(0.97, { damping: 20, stiffness: 300 }); }}
                onPressOut={() => { btnScale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }}
                disabled={loading}
                activeOpacity={0.9}
              >
                <Text style={s.btnText}>{loading ? 'Signing in…' : 'Sign in  →'}</Text>
              </TouchableOpacity>
            </Animated.View>
          </Animated.View>

          {/* Demo hint */}
          <Animated.View entering={FadeInDown.duration(440).delay(260)} style={s.demoHint}>
            <View style={s.demoHintLine} />
            <Text style={s.demoHintText}>No backend? Any email + password works in demo mode</Text>
            <View style={s.demoHintLine} />
          </Animated.View>

          {/* Register link */}
          <Animated.View entering={FadeInDown.duration(440).delay(300)} style={s.registerWrap}>
            <Text style={s.registerText}>Don't have an account?</Text>
            <TouchableOpacity onPress={() => router.push('/register')}>
              <Text style={s.registerLink}>  Create account</Text>
            </TouchableOpacity>
          </Animated.View>

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingBottom: 48, paddingTop: 24 },

  logoWrap:     { alignItems: 'center', marginBottom: 36, gap: 8 },
  logoMark:     { width: 60, height: 60, borderRadius: 18, backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.22, shadowRadius: 12, elevation: 8, marginBottom: 4 },
  logoMarkText: { fontSize: 28, fontWeight: '800', color: COLORS.parchment, letterSpacing: 1 },
  wordmark:     { fontSize: 16, fontWeight: '800', letterSpacing: 5, color: COLORS.ink },
  tagline:      { ...TYPE.micro, color: COLORS.textMuted, letterSpacing: 0.5 },

  headingWrap:  { marginBottom: 28, gap: 6 },
  heading:      { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, color: COLORS.ink, lineHeight: 36 },
  subheading:   { ...TYPE.bodyMed, color: COLORS.textMuted },

  form:         { gap: 0, marginBottom: 8 },

  errorBanner:  { backgroundColor: 'rgba(194,59,34,0.08)', borderRadius: RADIUS.md, borderWidth: 1, borderColor: 'rgba(194,59,34,0.2)', padding: 14, marginBottom: 16 },
  errorBannerText: { ...TYPE.bodySmall, color: COLORS.crimson, lineHeight: 20 },

  showHide:     { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '700' },

  forgotWrap: { alignSelf: 'flex-end', marginTop: -4, marginBottom: 20 },
  forgotText: { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '600' },

  btn:        { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 20, alignItems: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.2, shadowRadius: 14, elevation: 8 },
  btnLoading: { backgroundColor: COLORS.inkSoft },
  btnText:    { ...TYPE.titleLarge, color: COLORS.textInverse, letterSpacing: 0.2, fontSize: 17 },

  demoHint:      { flexDirection: 'row', alignItems: 'center', gap: 10, marginVertical: 24 },
  demoHintLine:  { flex: 1, height: 1, backgroundColor: COLORS.border },
  demoHintText:  { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'center', flexShrink: 1 },

  registerWrap: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  registerText: { ...TYPE.bodyMed, color: COLORS.textMuted },
  registerLink: { ...TYPE.bodyMed, color: COLORS.sage, fontWeight: '700' },
});
