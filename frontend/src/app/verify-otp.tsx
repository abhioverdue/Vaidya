/**
 * Vaidya — OTP Verification screen
 * 6 individual digit boxes, auto-advance, backspace-aware, countdown resend.
 * Works for both registration and password-reset flows via pendingReg.type.
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, Alert,
} from 'react-native';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeInDown, FadeIn,
  useSharedValue, useAnimatedStyle,
  withSpring, withTiming, withSequence,
  Easing,
} from 'react-native-reanimated';
import { useState, useRef, useEffect, useCallback } from 'react';
import * as Haptics from 'expo-haptics';

import { useAppStore } from '@/store';
import { authVerifyOtp, authRegister, authRequestOtp } from '@/services/auth';
import { COLORS, TYPE, RADIUS } from '@/constants';

const OTP_LENGTH = 6;

// ── OtpBox ────────────────────────────────────────────────────────────────────

function OtpBox({
  value, focused, hasError,
}: { value: string; focused: boolean; hasError: boolean }) {
  const scale = useSharedValue(1);

  useEffect(() => {
    if (value) {
      scale.value = withSequence(
        withSpring(1.15, { damping: 15, stiffness: 400 }),
        withSpring(1,    { damping: 12, stiffness: 300 }),
      );
    }
  }, [value]);

  const animStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  const borderColor = hasError
    ? COLORS.crimson
    : focused
    ? COLORS.sage
    : value
    ? COLORS.inkSoft
    : COLORS.border;

  const bg = hasError
    ? 'rgba(194,59,34,0.05)'
    : focused
    ? 'rgba(58,95,82,0.06)'
    : COLORS.surface;

  return (
    <Animated.View
      style={[
        ob.box,
        { borderColor, backgroundColor: bg, borderWidth: focused || value ? 2 : 1.5 },
        animStyle,
      ]}
    >
      {value ? (
        <Text style={ob.digit}>{value}</Text>
      ) : focused ? (
        <View style={ob.cursor} />
      ) : null}
    </Animated.View>
  );
}

const ob = StyleSheet.create({
  box:    { width: 48, height: 58, borderRadius: RADIUS.md, alignItems: 'center', justifyContent: 'center' },
  digit:  { fontSize: 24, fontWeight: '700', color: COLORS.ink, letterSpacing: -0.5 },
  cursor: { width: 2, height: 24, backgroundColor: COLORS.sage, borderRadius: 1 },
});

// ── Countdown ─────────────────────────────────────────────────────────────────

function Countdown({ seconds, onComplete }: { seconds: number; onComplete: () => void }) {
  const [remaining, setRemaining] = useState(seconds);

  useEffect(() => {
    setRemaining(seconds);
  }, [seconds]);

  useEffect(() => {
    if (remaining <= 0) { onComplete(); return; }
    const t = setTimeout(() => setRemaining((r) => r - 1), 1000);
    return () => clearTimeout(t);
  }, [remaining]);

  if (remaining <= 0) return null;
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  return (
    <Text style={cd.text}>
      Resend code in {m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`}
    </Text>
  );
}

const cd = StyleSheet.create({
  text: { ...TYPE.bodySmall, color: COLORS.textMuted, textAlign: 'center' },
});

// ── VerifyOtpScreen ───────────────────────────────────────────────────────────

export default function VerifyOtpScreen() {
  const { pendingReg, setPendingReg, setAuth } = useAppStore();

  // Guard: if pendingReg is missing (direct navigation / back-stack flush), go back
  useEffect(() => {
    if (!pendingReg) router.replace('/login' as any);
  }, []);

  const [digits,    setDigits]    = useState<string[]>(Array(OTP_LENGTH).fill(''));
  const [focusIdx,  setFocusIdx]  = useState(0);
  const [loading,   setLoading]   = useState(false);
  const [hasError,  setHasError]  = useState(false);
  const [errorMsg,  setErrorMsg]  = useState('');
  const [canResend, setCanResend] = useState(false);
  const [resendKey, setResendKey] = useState(0);   // bump to restart countdown

  const refs = useRef<Array<TextInput | null>>(Array(OTP_LENGTH).fill(null));

  // Focus first box on mount
  useEffect(() => {
    setTimeout(() => refs.current[0]?.focus(), 300);
  }, []);

  const otp = digits.join('');

  // Auto-submit when all boxes filled
  useEffect(() => {
    if (otp.length === OTP_LENGTH && !otp.includes('')) {
      handleVerify();
    }
  }, [otp]);

  const handleDigitChange = useCallback((text: string, idx: number) => {
    const cleaned = text.replace(/\D/g, '').slice(-1);
    const next    = [...digits];
    next[idx]     = cleaned;
    setDigits(next);
    setHasError(false);
    setErrorMsg('');
    if (cleaned && idx < OTP_LENGTH - 1) {
      refs.current[idx + 1]?.focus();
      setFocusIdx(idx + 1);
    }
  }, [digits]);

  const handleKeyPress = useCallback((e: any, idx: number) => {
    if (e.nativeEvent.key === 'Backspace') {
      if (digits[idx]) {
        const next = [...digits];
        next[idx]  = '';
        setDigits(next);
      } else if (idx > 0) {
        const next = [...digits];
        next[idx - 1] = '';
        setDigits(next);
        refs.current[idx - 1]?.focus();
        setFocusIdx(idx - 1);
      }
    }
  }, [digits]);

  // Shake animation for wrong OTP
  const shakeX = useSharedValue(0);
  const shakeStyle = useAnimatedStyle(() => ({ transform: [{ translateX: shakeX.value }] }));

  function triggerShake() {
    shakeX.value = withSequence(
      withTiming(-10, { duration: 60 }),
      withTiming(10,  { duration: 60 }),
      withTiming(-8,  { duration: 60 }),
      withTiming(8,   { duration: 60 }),
      withTiming(0,   { duration: 60 }),
    );
  }

  const btnScale = useSharedValue(1);
  const btnStyle = useAnimatedStyle(() => ({ transform: [{ scale: btnScale.value }] }));

  async function handleVerify() {
    if (otp.length < OTP_LENGTH || loading) return;
    setLoading(true);
    setHasError(false);
    setErrorMsg('');
    try {
      const res = await authVerifyOtp(pendingReg?.phone ?? '', otp);
      if (!res.valid) {
        setHasError(true);
        setErrorMsg(res.message || 'Invalid OTP. Please check and try again.');
        triggerShake();
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        setLoading(false);
        return;
      }

      if (pendingReg?.type === 'register') {
        // Complete registration
        const authRes = await authRegister(
          pendingReg.name,
          pendingReg.phone,
          pendingReg.password,
        );
        await setAuth(authRes.user, authRes.access_token);
        setPendingReg(null);
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        router.replace('/');
      } else {
        // Password reset — store the verified OTP so reset-password can forward it
        // to the backend (authResetPassword requires the original OTP, not a placeholder)
        setPendingReg(pendingReg ? { ...pendingReg, type: 'reset', otp } : null);
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        router.replace('/reset-password');
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? err?.message ?? 'Verification failed.';
      setHasError(true);
      setErrorMsg(String(msg));
      triggerShake();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (!pendingReg) return;
    setCanResend(false);
    setResendKey((k) => k + 1);
    setDigits(Array(OTP_LENGTH).fill(''));
    setHasError(false);
    setErrorMsg('');
    refs.current[0]?.focus();
    setFocusIdx(0);
    try {
      await authRequestOtp(pendingReg.phone, pendingReg.type === 'register' ? 'register' : 'reset');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {}
  }

  const phone = pendingReg?.phone ?? '';
  const maskedPhone = phone.length === 10
    ? `+91 ${phone.slice(0, 2)}••••${phone.slice(-4)}`
    : phone;

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={s.container}>

          {/* Back button */}
          <Animated.View entering={FadeInDown.duration(380)} style={s.headerRow}>
            <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
              <View style={s.backCircle}>
                <Text style={s.backGlyph}>←</Text>
              </View>
            </TouchableOpacity>
          </Animated.View>

          {/* Header */}
          <Animated.View entering={FadeInDown.duration(440).delay(60)} style={s.headingWrap}>
            <Text style={s.heading}>Enter OTP</Text>
            <Text style={s.subheading}>
              We sent a 6-digit code to{'\n'}
              <Text style={s.phoneHighlight}>{maskedPhone}</Text>
            </Text>
          </Animated.View>

          {/* Demo hint */}
          <Animated.View entering={FadeIn.duration(440).delay(120)} style={s.demoBox}>
            <Text style={s.demoBoxText}>Demo mode: use code{' '}</Text>
            <Text style={s.demoCode}>123456</Text>
          </Animated.View>

          {/* OTP boxes */}
          <Animated.View
            entering={FadeInDown.duration(440).delay(180)}
            style={[s.boxesWrap, shakeStyle]}
          >
            <View style={s.boxes}>
              {Array.from({ length: OTP_LENGTH }, (_, i) => (
                <TouchableOpacity
                  key={i}
                  onPress={() => { refs.current[i]?.focus(); setFocusIdx(i); }}
                  activeOpacity={0.9}
                >
                  <OtpBox value={digits[i]} focused={focusIdx === i} hasError={hasError} />
                  {/* Hidden real TextInput stacked over visual box */}
                  <TextInput
                    ref={(r) => { refs.current[i] = r; }}
                    style={s.hiddenInput}
                    value={digits[i]}
                    onChangeText={(t) => handleDigitChange(t, i)}
                    onKeyPress={(e) => handleKeyPress(e, i)}
                    onFocus={() => setFocusIdx(i)}
                    onBlur={() => setFocusIdx(-1)}
                    keyboardType="number-pad"
                    maxLength={1}
                    caretHidden
                    selectTextOnFocus
                  />
                </TouchableOpacity>
              ))}
            </View>

            {hasError && (
              <Animated.Text entering={FadeIn.duration(220)} style={s.errorText}>
                {errorMsg}
              </Animated.Text>
            )}
          </Animated.View>

          {/* Verify button */}
          <Animated.View entering={FadeInDown.duration(440).delay(260)} style={{ width: '100%' }}>
            <Animated.View style={btnStyle}>
              <TouchableOpacity
                style={[s.btn, (loading || otp.length < OTP_LENGTH) && s.btnDisabled]}
                onPress={handleVerify}
                onPressIn={() => { btnScale.value = withSpring(0.97, { damping: 20, stiffness: 300 }); }}
                onPressOut={() => { btnScale.value = withSpring(1,    { damping: 20, stiffness: 300 }); }}
                disabled={loading || otp.length < OTP_LENGTH}
                activeOpacity={0.9}
              >
                <Text style={s.btnText}>
                  {loading ? 'Verifying…' : 'Verify  →'}
                </Text>
              </TouchableOpacity>
            </Animated.View>
          </Animated.View>

          {/* Resend */}
          <Animated.View entering={FadeInDown.duration(440).delay(320)} style={s.resendWrap}>
            {canResend ? (
              <TouchableOpacity onPress={handleResend} style={s.resendBtn}>
                <Text style={s.resendText}>Resend code</Text>
              </TouchableOpacity>
            ) : (
              <Countdown
                key={resendKey}
                seconds={60}
                onComplete={() => setCanResend(true)}
              />
            )}
          </Animated.View>

        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:       { flex: 1, backgroundColor: COLORS.parchment },
  container:  { flex: 1, paddingHorizontal: 28, paddingTop: 16, alignItems: 'center', gap: 0 },

  headerRow:  { width: '100%', marginBottom: 16 },
  backBtn:    { width: 40 },
  backCircle: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backGlyph:  { fontSize: 18, color: COLORS.ink, marginTop: -1 },

  headingWrap:   { width: '100%', marginBottom: 20, gap: 8 },
  heading:       { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, color: COLORS.ink },
  subheading:    { ...TYPE.bodyLarge, color: COLORS.textMuted, lineHeight: 26 },
  phoneHighlight:{ fontWeight: '700', color: COLORS.ink },

  demoBox:     { backgroundColor: COLORS.sageGhost, borderRadius: RADIUS.md, paddingVertical: 10, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', marginBottom: 28, borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)' },
  demoBoxText: { ...TYPE.bodySmall, color: COLORS.sage },
  demoCode:    { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '800', letterSpacing: 2 },

  boxesWrap: { width: '100%', alignItems: 'center', marginBottom: 24, gap: 10 },
  boxes:     { flexDirection: 'row', gap: 10, justifyContent: 'center' },

  hiddenInput: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    opacity: 0, fontSize: 1,
  },

  errorText: { ...TYPE.bodySmall, color: COLORS.crimson, textAlign: 'center', marginTop: 4 },

  btn:         { width: '100%', backgroundColor: COLORS.ink, borderRadius: RADIUS.xl, paddingVertical: 20, alignItems: 'center', shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.2, shadowRadius: 14, elevation: 8 },
  btnDisabled: { backgroundColor: COLORS.borderMid, shadowOpacity: 0 },
  btnText:     { ...TYPE.titleLarge, color: COLORS.textInverse, letterSpacing: 0.2, fontSize: 17 },

  resendWrap: { marginTop: 20, alignItems: 'center' },
  resendBtn:  { paddingVertical: 8, paddingHorizontal: 16 },
  resendText: { ...TYPE.bodyMed, color: COLORS.sage, fontWeight: '700' },
});
