/**
 * Vaidya — Register screen
 * Name + mobile + password + confirm. Sends OTP → verify-otp.
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeInDown,
  useSharedValue, useAnimatedStyle, withSpring, withTiming,
  interpolate, Easing,
} from 'react-native-reanimated';
import { useState, useRef, useCallback } from 'react';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { authRequestOtp } from '@/services/auth';
import { COLORS, TYPE, RADIUS } from '@/constants';

// ── FloatingLabelInput (same as login, inlined for isolation) ─────────────────

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
  autoCapitalize?: 'none' | 'words' | 'sentences' | 'characters';
  inputRef?:       React.RefObject<TextInput>;
}

function FloatingLabelInput({
  label, value, onChangeText, keyboardType, secureTextEntry, autoComplete,
  returnKeyType, onSubmitEditing, maxLength, prefix, rightEl, error,
  autoFocus, autoCapitalize = 'none', inputRef,
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
            autoCapitalize={autoCapitalize}
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

// ── PasswordStrength ──────────────────────────────────────────────────────────

function PasswordStrength({ password }: { password: string }) {
  if (!password) return null;
  const score = [
    password.length >= 8,
    /[A-Z]/.test(password),
    /[0-9]/.test(password),
    /[^A-Za-z0-9]/.test(password),
  ].filter(Boolean).length;

  const label = score <= 1 ? 'Weak' : score <= 2 ? 'Fair' : score <= 3 ? 'Good' : 'Strong';
  const color = score <= 1 ? COLORS.crimson : score <= 2 ? COLORS.gold : score <= 3 ? COLORS.sage : COLORS.t1;

  return (
    <View style={ps.wrap}>
      <View style={ps.bars}>
        {[1, 2, 3, 4].map((i) => (
          <View
            key={i}
            style={[ps.bar, { backgroundColor: i <= score ? color : COLORS.border }]}
          />
        ))}
      </View>
      <Text style={[ps.label, { color }]}>{label}</Text>
    </View>
  );
}

const ps = StyleSheet.create({
  wrap:  { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: -10, marginBottom: 10, paddingHorizontal: 4 },
  bars:  { flexDirection: 'row', gap: 4, flex: 1 },
  bar:   { flex: 1, height: 3, borderRadius: 2 },
  label: { ...TYPE.micro, fontWeight: '700', width: 44, textAlign: 'right' },
});

// ── RegisterScreen ────────────────────────────────────────────────────────────

export default function RegisterScreen() {
  const setPendingReg = useAppStore((s) => s.setPendingReg);

  const [name,     setName]     = useState('');
  const [phone,    setPhone]    = useState('');
  const [password, setPassword] = useState('');
  const [confirm,  setConfirm]  = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [errors,   setErrors]   = useState<Record<string, string>>({});

  const phoneRef    = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);
  const confirmRef  = useRef<TextInput>(null);

  const btnScale = useSharedValue(1);
  const btnStyle = useAnimatedStyle(() => ({ transform: [{ scale: btnScale.value }] }));

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!name.trim())                       e.name     = 'Enter your full name';
    if (!phone.trim())                      e.phone    = 'Enter your mobile number';
    else if (!/^\d{10}$/.test(phone.trim())) e.phone   = 'Enter a valid 10-digit number';
    if (!password)                           e.password = 'Enter a password';
    else if (password.length < 6)            e.password = 'Password must be at least 6 characters';
    if (!confirm)                            e.confirm  = 'Confirm your password';
    else if (confirm !== password)           e.confirm  = 'Passwords do not match';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSendOtp() {
    if (!validate()) { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error); return; }
    setLoading(true);
    setErrors({});
    try {
      await authRequestOtp(phone.trim(), 'register');
      setPendingReg({ name: name.trim(), phone: phone.trim(), password, type: 'register' });
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.push('/verify-otp');
    } catch (err: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const msg = err?.response?.data?.detail ?? err?.message ?? 'Could not send OTP. Try again.';
      setErrors({ general: String(msg) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

          {/* Header */}
          <Animated.View entering={FadeInDown.duration(400)} style={s.headerRow}>
            <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
              <View style={s.backCircle}>
                <Text style={s.backGlyph}>←</Text>
              </View>
            </TouchableOpacity>
          </Animated.View>

          {/* Heading */}
          <Animated.View entering={FadeInDown.duration(440).delay(60)} style={s.headingWrap}>
            <Text style={s.heading}>Create account</Text>
            <Text style={s.subheading}>Join Vaidya — free AI health triage for India</Text>
          </Animated.View>

          {/* Form */}
          <Animated.View entering={FadeInDown.duration(440).delay(140)} style={s.form}>
            {errors.general && (
              <View style={s.errorBanner}>
                <Text style={s.errorBannerText}>{errors.general}</Text>
              </View>
            )}

            <FloatingLabelInput
              label="Full name"
              value={name}
              onChangeText={(t) => { setName(t); setErrors((e) => ({ ...e, name: undefined as any })); }}
              autoCapitalize="words"
              returnKeyType="next"
              onSubmitEditing={() => phoneRef.current?.focus()}
              error={errors.name}
              autoFocus
            />

            <FloatingLabelInput
              label="Mobile number"
              value={phone}
              onChangeText={(t) => { setPhone(t.replace(/\D/g, '')); setErrors((e) => ({ ...e, phone: undefined as any })); }}
              keyboardType="phone-pad"
              autoComplete="tel"
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              maxLength={10}
              prefix="+91"
              error={errors.phone}
              inputRef={phoneRef}
            />

            <FloatingLabelInput
              label="Password"
              value={password}
              onChangeText={(t) => { setPassword(t); setErrors((e) => ({ ...e, password: undefined as any })); }}
              secureTextEntry={!showPass}
              returnKeyType="next"
              onSubmitEditing={() => confirmRef.current?.focus()}
              error={errors.password}
              inputRef={passwordRef}
              rightEl={
                <TouchableOpacity onPress={() => setShowPass((v) => !v)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Text style={s.showHide}>{showPass ? 'Hide' : 'Show'}</Text>
                </TouchableOpacity>
              }
            />
            <PasswordStrength password={password} />

            <FloatingLabelInput
              label="Confirm password"
              value={confirm}
              onChangeText={(t) => { setConfirm(t); setErrors((e) => ({ ...e, confirm: undefined as any })); }}
              secureTextEntry={!showPass}
              returnKeyType="done"
              onSubmitEditing={handleSendOtp}
              error={errors.confirm}
              inputRef={confirmRef}
            />
          </Animated.View>

          {/* OTP notice */}
          <Animated.View entering={FadeInDown.duration(440).delay(200)} style={s.otpNotice}>
            <Text style={s.otpNoticeText}>
              We'll send a 6-digit OTP to verify your mobile number
            </Text>
          </Animated.View>

          {/* CTA */}
          <Animated.View entering={FadeInDown.duration(440).delay(240)} style={{ marginBottom: 24 }}>
            <Animated.View style={btnStyle}>
              <TouchableOpacity
                style={[s.btn, loading && s.btnLoading]}
                onPress={handleSendOtp}
                onPressIn={() => { btnScale.value = withSpring(0.97, { damping: 20, stiffness: 300 }); }}
                onPressOut={() => { btnScale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }}
                disabled={loading}
                activeOpacity={0.9}
              >
                <Text style={s.btnText}>{loading ? 'Sending OTP…' : 'Send OTP  →'}</Text>
              </TouchableOpacity>
            </Animated.View>
          </Animated.View>

          {/* Login link */}
          <Animated.View entering={FadeInDown.duration(440).delay(280)} style={s.loginWrap}>
            <Text style={s.loginText}>Already have an account?</Text>
            <TouchableOpacity onPress={() => router.replace('/login')}>
              <Text style={s.loginLink}>  Sign in</Text>
            </TouchableOpacity>
          </Animated.View>

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingBottom: 48, paddingTop: 16 },

  headerRow: { marginBottom: 16 },
  backBtn:   { width: 40 },
  backCircle:{ width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backGlyph: { fontSize: 18, color: COLORS.ink, marginTop: -1 },

  headingWrap: { marginBottom: 28, gap: 6 },
  heading:     { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, color: COLORS.ink, lineHeight: 36 },
  subheading:  { ...TYPE.bodyMed, color: COLORS.textMuted },

  form:         { gap: 0, marginBottom: 0 },
  errorBanner:  { backgroundColor: 'rgba(194,59,34,0.08)', borderRadius: RADIUS.md, borderWidth: 1, borderColor: 'rgba(194,59,34,0.2)', padding: 14, marginBottom: 16 },
  errorBannerText: { ...TYPE.bodySmall, color: COLORS.crimson, lineHeight: 20 },
  showHide:     { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '700' },

  otpNotice: { backgroundColor: COLORS.sageGhost, borderRadius: RADIUS.md, padding: 14, borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)', marginBottom: 20 },
  otpNoticeText: { ...TYPE.bodySmall, color: COLORS.sage, textAlign: 'center', lineHeight: 20 },

  btn:        { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 20, alignItems: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.2, shadowRadius: 14, elevation: 8 },
  btnLoading: { backgroundColor: COLORS.inkSoft },
  btnText:    { ...TYPE.titleLarge, color: COLORS.textInverse, letterSpacing: 0.2, fontSize: 17 },

  loginWrap: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  loginText: { ...TYPE.bodyMed, color: COLORS.textMuted },
  loginLink: { ...TYPE.bodyMed, color: COLORS.sage, fontWeight: '700' },
});
