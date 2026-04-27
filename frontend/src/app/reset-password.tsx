/**
 * Vaidya — Reset Password screen
 * Logged-out: enter email → Firebase sends password reset link
 * Logged-in: enter current password + new password
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeInDown, FadeIn,
  useSharedValue, useAnimatedStyle, withSpring, withTiming,
  interpolate, Easing,
} from 'react-native-reanimated';
import { useState, useRef, useCallback } from 'react';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { authSendPasswordReset, authChangePassword } from '@/services/auth';
import { COLORS, TYPE, RADIUS } from '@/constants';

// ── FloatingLabelInput ────────────────────────────────────────────────────────

interface FLInputProps {
  label: string; value: string; onChangeText: (t: string) => void;
  keyboardType?: any; secureTextEntry?: boolean;
  returnKeyType?: any; onSubmitEditing?: () => void;
  maxLength?: number; prefix?: string;
  rightEl?: React.ReactNode; error?: string; autoFocus?: boolean;
  inputRef?: React.RefObject<TextInput>;
}

function FloatingLabelInput({ label, value, onChangeText, keyboardType, secureTextEntry,
  returnKeyType, onSubmitEditing, maxLength, prefix, rightEl, error, autoFocus, inputRef }: FLInputProps) {
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
      ? (focused ? COLORS.sage : COLORS.textMuted) : COLORS.textFaint,
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

// ── ResetPasswordScreen ───────────────────────────────────────────────────────

export default function ResetPasswordScreen() {
  const { user } = useAppStore();

  // If user is already signed in → real Firebase change-password flow
  const isLoggedIn = !!user;

  // Forgot-password state
  const [email,   setEmail]   = useState('');
  const [loading, setLoading] = useState(false);
  const [errors,  setErrors]  = useState<Record<string, string>>({});

  // Logged-in change-password state
  const [currentPass, setCurrentPass] = useState('');

  // Phase 2 / logged-in new password state
  const [newPass,    setNewPass]    = useState('');
  const [confirmPass,setConfirmPass]= useState('');
  const [showPass,   setShowPass]   = useState(false);
  const [success,    setSuccess]    = useState(false);

  const newPassRef  = useRef<TextInput>(null);
  const confirmRef  = useRef<TextInput>(null);

  const btnScale = useSharedValue(1);
  const btnStyle = useAnimatedStyle(() => ({ transform: [{ scale: btnScale.value }] }));

  // ── Forgot-password: send Firebase reset email ────────────────────────────
  async function handleSendReset() {
    const e: Record<string, string> = {};
    if (!email.trim())                                              e.email = 'Enter your email address';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))     e.email = 'Enter a valid email address';
    if (Object.keys(e).length) {
      setErrors(e);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      return;
    }
    setLoading(true);
    setErrors({});
    try {
      await authSendPasswordReset(email.trim());
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setSuccess(true);
    } catch (err: any) {
      const msg = err?.message ?? 'Could not send reset email. Please try again.';
      setErrors({ general: String(msg) });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setLoading(false);
    }
  }

  // ── Logged-in: real Firebase password change ───────────────────────────────
  async function handleChangePassword() {
    const e: Record<string, string> = {};
    if (!currentPass)                e.currentPass  = 'Enter your current password';
    if (!newPass)                    e.newPass      = 'Enter a new password';
    else if (newPass.length < 6)     e.newPass      = 'Password must be at least 6 characters';
    if (!confirmPass)                e.confirmPass  = 'Confirm your new password';
    else if (confirmPass !== newPass) e.confirmPass = 'Passwords do not match';
    if (Object.keys(e).length) { setErrors(e); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error); return; }
    setLoading(true); setErrors({});
    try {
      await authChangePassword(user!.email, currentPass, newPass);
      setSuccess(true);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (err: any) {
      setErrors({ general: err?.message ?? 'Password change failed.' });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally { setLoading(false); }
  }

  // ── Success state ──────────────────────────────────────────────────────────
  if (success) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.successContainer}>
          <Animated.View entering={FadeIn.duration(500)} style={s.successWrap}>
            <View style={s.successIcon}>
              <Text style={s.successIconText}>✓</Text>
            </View>
            <Text style={s.successTitle}>{isLoggedIn ? 'Password changed!' : 'Check your inbox'}</Text>
            <Text style={s.successSub}>
              {isLoggedIn
                ? 'Your password has been updated successfully.'
                : `A password reset link has been sent to ${email || 'your email'}. Check your inbox and follow the link.`}
            </Text>
            <TouchableOpacity
              style={s.btn}
              onPress={() => isLoggedIn ? router.back() : router.replace('/login')}
            >
              <Text style={s.btnText}>{isLoggedIn ? 'Done  →' : 'Sign in  →'}</Text>
            </TouchableOpacity>
          </Animated.View>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

          {/* Header */}
          <Animated.View entering={FadeInDown.duration(380)} style={s.headerRow}>
            <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
              <View style={s.backCircle}>
                <Text style={s.backGlyph}>←</Text>
              </View>
            </TouchableOpacity>
          </Animated.View>

          {/* Heading */}
          <Animated.View entering={FadeInDown.duration(440).delay(60)} style={s.headingWrap}>
            <Text style={s.heading}>
              {isLoggedIn ? 'Change password' : 'Reset password'}
            </Text>
            <Text style={s.subheading}>
              {isLoggedIn
                ? 'Enter your current password then choose a new one'
                : 'Enter your email address and we\'ll send you a reset link'}
            </Text>
          </Animated.View>

          {/* Error banner */}
          {errors.general && (
            <Animated.View entering={FadeIn.duration(220)} style={s.errorBanner}>
              <Text style={s.errorBannerText}>{errors.general}</Text>
            </Animated.View>
          )}

          {/* Logged-in: real change-password form */}
          {isLoggedIn && (
            <Animated.View entering={FadeInDown.duration(440).delay(140)} style={{ gap: 0 }}>
              <FloatingLabelInput
                label="Current password"
                value={currentPass}
                onChangeText={(t) => { setCurrentPass(t); setErrors({}); }}
                secureTextEntry={!showPass}
                returnKeyType="next"
                onSubmitEditing={() => newPassRef.current?.focus()}
                error={errors.currentPass}
                autoFocus
              />
              <FloatingLabelInput
                label="New password"
                value={newPass}
                onChangeText={(t) => { setNewPass(t); setErrors({}); }}
                secureTextEntry={!showPass}
                returnKeyType="next"
                onSubmitEditing={() => confirmRef.current?.focus()}
                inputRef={newPassRef}
                error={errors.newPass}
                rightEl={
                  <TouchableOpacity onPress={() => setShowPass((v) => !v)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Text style={s.showHide}>{showPass ? 'Hide' : 'Show'}</Text>
                  </TouchableOpacity>
                }
              />
              <FloatingLabelInput
                label="Confirm new password"
                value={confirmPass}
                onChangeText={(t) => { setConfirmPass(t); setErrors({}); }}
                secureTextEntry={!showPass}
                returnKeyType="done"
                onSubmitEditing={handleChangePassword}
                error={errors.confirmPass}
                inputRef={confirmRef}
              />
            </Animated.View>
          )}

          {/* Forgot-password — email input */}
          {!isLoggedIn && (
            <Animated.View entering={FadeInDown.duration(440).delay(140)}>
              <FloatingLabelInput
                label="Email address"
                value={email}
                onChangeText={(t) => { setEmail(t.trim()); setErrors({}); }}
                keyboardType="email-address"
                returnKeyType="done"
                onSubmitEditing={handleSendReset}
                error={errors.email}
                autoFocus
              />
            </Animated.View>
          )}

          {/* CTA */}
          <Animated.View entering={FadeInDown.duration(440).delay(200)} style={{ marginTop: 8 }}>
            <Animated.View style={btnStyle}>
              <TouchableOpacity
                style={[s.btn, loading && s.btnLoading]}
                onPress={isLoggedIn ? handleChangePassword : handleSendReset}
                onPressIn={() => { btnScale.value = withSpring(0.97, { damping: 20, stiffness: 300 }); }}
                onPressOut={() => { btnScale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }}
                disabled={loading}
                activeOpacity={0.9}
              >
                <Text style={s.btnText}>
                  {loading
                    ? (isLoggedIn ? 'Saving…' : 'Sending…')
                    : (isLoggedIn ? 'Save password  →' : 'Send reset link  →')}
                </Text>
              </TouchableOpacity>
            </Animated.View>
          </Animated.View>

          {/* Back to login (only on forgot-password flow) */}
          {!isLoggedIn && (
            <Animated.View entering={FadeInDown.duration(440).delay(260)} style={s.loginLinkWrap}>
              <Text style={s.loginLinkText}>Remember your password?</Text>
              <TouchableOpacity onPress={() => router.replace('/login')}>
                <Text style={s.loginLink}>  Sign in</Text>
              </TouchableOpacity>
            </Animated.View>
          )}

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.parchment },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingBottom: 48, paddingTop: 16 },

  successContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  successWrap:      { alignItems: 'center', gap: 16, width: '100%' },
  successIcon:      { width: 80, height: 80, borderRadius: 40, backgroundColor: COLORS.sageGhost, borderWidth: 2, borderColor: COLORS.sage, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  successIconText:  { fontSize: 34, color: COLORS.sage, fontWeight: '700' },
  successTitle:     { fontSize: 28, fontWeight: '700', letterSpacing: -0.5, color: COLORS.ink },
  successSub:       { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center', lineHeight: 23, marginBottom: 8 },

  headerRow:  { marginBottom: 16 },
  backBtn:    { width: 40 },
  backCircle: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backGlyph:  { fontSize: 18, color: COLORS.ink, marginTop: -1 },

  headingWrap: { marginBottom: 28, gap: 6 },
  heading:     { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, color: COLORS.ink, lineHeight: 36 },
  subheading:  { ...TYPE.bodyMed, color: COLORS.textMuted, lineHeight: 23 },

  errorBanner:     { backgroundColor: 'rgba(194,59,34,0.08)', borderRadius: RADIUS.md, borderWidth: 1, borderColor: 'rgba(194,59,34,0.2)', padding: 14, marginBottom: 16 },
  errorBannerText: { ...TYPE.bodySmall, color: COLORS.crimson, lineHeight: 20 },

  showHide: { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '700' },

  btn:        { backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 20, alignItems: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.2, shadowRadius: 14, elevation: 8 },
  btnLoading: { backgroundColor: COLORS.inkSoft },
  btnText:    { ...TYPE.titleLarge, color: COLORS.textInverse, letterSpacing: 0.2, fontSize: 17 },

  loginLinkWrap: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: 24 },
  loginLinkText: { ...TYPE.bodyMed, color: COLORS.textMuted },
  loginLink:     { ...TYPE.bodyMed, color: COLORS.sage, fontWeight: '700' },
});
