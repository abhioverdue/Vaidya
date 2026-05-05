/**
 * Vaidya — Teleconsult Booking Screen
 * Receives slot params via useLocalSearchParams, submits to POST /care/teleconsult/book
 * Demo fallback: auto-confirms with demo booking IDs
 */

import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  TextInput, ActivityIndicator, Linking, KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { apiClient } from '@/services/api';
import { markDemoMode } from '@/services/demoData';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatAvailableAt(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();
    const timeStr = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
    return isToday ? `Today at ${timeStr}` : d.toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' }) + ` at ${timeStr}`;
  } catch {
    return iso;
  }
}

// ── Booking confirmation card ─────────────────────────────────────────────────

function ConfirmationCard({
  bookingId,
  confirmationCode,
  availableAt,
  bookingUrl,
  onCancel,
  cancelling,
}: {
  bookingId: string;
  confirmationCode: string;
  availableAt: string;
  bookingUrl: string;
  onCancel: () => void;
  cancelling: boolean;
}) {
  return (
    <Animated.View entering={FadeInDown.duration(320)} style={conf.wrap}>
      <View style={conf.iconRow}>
        <View style={conf.checkCircle}>
          <Text style={conf.checkText}>✓</Text>
        </View>
      </View>
      <Text style={conf.title}>Appointment Confirmed</Text>
      <Text style={conf.sub}>Your teleconsult has been booked successfully.</Text>

      <View style={conf.detailsCard}>
        <View style={conf.detailRow}>
          <Text style={conf.detailLabel}>Booking ID</Text>
          <Text style={conf.detailValue}>{bookingId}</Text>
        </View>
        <View style={conf.divider} />
        <View style={conf.detailRow}>
          <Text style={conf.detailLabel}>Confirmation code</Text>
          <Text style={[conf.detailValue, { fontWeight: '700', color: COLORS.sage }]}>{confirmationCode}</Text>
        </View>
        <View style={conf.divider} />
        <View style={conf.detailRow}>
          <Text style={conf.detailLabel}>Scheduled time</Text>
          <Text style={conf.detailValue}>{formatAvailableAt(availableAt)}</Text>
        </View>
      </View>

      <TouchableOpacity
        style={conf.joinBtn}
        onPress={() => Linking.openURL(bookingUrl).catch(() => {})}
        activeOpacity={0.82}
      >
        <Text style={conf.joinBtnText}>Join at {formatAvailableAt(availableAt)}</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={conf.cancelLink}
        onPress={onCancel}
        disabled={cancelling}
        activeOpacity={0.7}
      >
        {cancelling ? (
          <ActivityIndicator size="small" color={COLORS.crimson} />
        ) : (
          <Text style={conf.cancelLinkText}>Cancel booking</Text>
        )}
      </TouchableOpacity>
    </Animated.View>
  );
}

const conf = StyleSheet.create({
  wrap:        { alignItems: 'center', paddingVertical: 8, gap: 12 },
  iconRow:     { marginBottom: 4 },
  checkCircle: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: COLORS.sageGhost,
    borderWidth: 2, borderColor: COLORS.sage,
    alignItems: 'center', justifyContent: 'center',
  },
  checkText:   { fontSize: 28, color: COLORS.sage, fontWeight: '700' },
  title:       { ...TYPE.headlineLarge, color: COLORS.ink, textAlign: 'center' },
  sub:         { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center' },
  detailsCard: {
    width: '100%', backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border,
    overflow: 'hidden', marginTop: 4,
  },
  detailRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12 },
  detailLabel: { ...TYPE.bodyMed, color: COLORS.textMuted },
  detailValue: { ...TYPE.bodyMed, color: COLORS.ink, flex: 1, textAlign: 'right' },
  divider:     { height: 1, backgroundColor: COLORS.border, marginHorizontal: 16 },
  joinBtn:     {
    width: '100%', backgroundColor: COLORS.sage,
    borderRadius: RADIUS.lg, paddingVertical: 16,
    alignItems: 'center', marginTop: 4,
  },
  joinBtnText: { ...TYPE.titleLarge, color: '#fff' },
  cancelLink:  { paddingVertical: 8 },
  cancelLinkText: { ...TYPE.bodyMed, color: COLORS.crimson, textDecorationLine: 'underline' },
});

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function TeleconsultBookScreen() {
  const params = useLocalSearchParams<{
    doctor_name: string;
    specialty:   string;
    available_at: string;
    platform:    string;
    booking_url: string;
  }>();

  const [patientName,  setPatientName]  = useState('');
  const [patientPhone, setPatientPhone] = useState('');
  const [symptoms,     setSymptoms]     = useState('');
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState<string | null>(null);
  const [booked,       setBooked]       = useState<{
    booking_id: string;
    confirmation_code: string;
  } | null>(null);
  const [cancelling,   setCancelling]   = useState(false);

  const doctorName  = params.doctor_name  ?? 'Dr. Unknown';
  const specialty   = params.specialty    ?? 'General Medicine';
  const availableAt = params.available_at ?? new Date().toISOString();
  const platform    = params.platform     ?? 'eSanjeevani';
  const bookingUrl  = params.booking_url  ?? 'https://esanjeevaniopd.in';

  async function handleBook() {
    if (!patientName.trim()) { setError('Please enter patient name.'); return; }
    if (!patientPhone.trim() || patientPhone.trim().length < 10) { setError('Please enter a valid 10-digit phone number.'); return; }
    if (!symptoms.trim()) { setError('Please describe the symptoms.'); return; }
    setError(null);
    setLoading(true);
    try {
      const { data } = await apiClient.post('/care/teleconsult/book', {
        doctor_name:  doctorName,
        specialty,
        available_at: availableAt,
        platform,
        booking_url:  bookingUrl,
        patient_name:  patientName.trim(),
        patient_phone: `+91${patientPhone.trim().replace(/^(\+91|0)/, '')}`,
        symptoms_summary: symptoms.trim(),
      });
      setBooked({ booking_id: data.booking_id, confirmation_code: data.confirmation_code });
    } catch {
      markDemoMode();
      await new Promise((r) => setTimeout(r, 1200));
      setBooked({ booking_id: 'demo-booking-001', confirmation_code: 'VDY-DEMO-001' });
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel() {
    if (!booked) return;
    setCancelling(true);
    try {
      await apiClient.post(`/care/teleconsult/${booked.booking_id}/cancel`);
    } catch {
      // Always succeed silently — booking cancel has demo fallback
    } finally {
      setCancelling(false);
      router.back();
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backArrow}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Book Teleconsult</Text>
        <View style={styles.headerSpacer} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Doctor card */}
          <Animated.View entering={FadeInDown.duration(280)} style={styles.doctorCard}>
            <View style={styles.doctorCardTop}>
              <View style={styles.doctorAvatar}>
                <Text style={styles.doctorAvatarText}>
                  {doctorName.split(' ').slice(-1)[0]?.charAt(0) ?? 'D'}
                </Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.doctorName}>{doctorName}</Text>
                <Text style={styles.doctorSpecialty}>{specialty}</Text>
              </View>
              <View style={styles.platformBadge}>
                <Text style={styles.platformBadgeText}>{platform}</Text>
              </View>
            </View>
            <View style={styles.doctorCardTime}>
              <Text style={styles.timeIcon}>◷</Text>
              <Text style={styles.timeText}>{formatAvailableAt(availableAt)}</Text>
            </View>
          </Animated.View>

          {booked ? (
            <Animated.View entering={FadeInDown.duration(320)}>
              <ConfirmationCard
                bookingId={booked.booking_id}
                confirmationCode={booked.confirmation_code}
                availableAt={availableAt}
                bookingUrl={bookingUrl}
                onCancel={handleCancel}
                cancelling={cancelling}
              />
            </Animated.View>
          ) : (
            <>
              {/* Form */}
              <Animated.View entering={FadeInDown.duration(280).delay(60)} style={styles.formSection}>
                <Text style={styles.formLabel}>Patient name</Text>
                <TextInput
                  style={styles.input}
                  placeholder="Full name"
                  placeholderTextColor={COLORS.textFaint}
                  value={patientName}
                  onChangeText={setPatientName}
                  autoCapitalize="words"
                  returnKeyType="next"
                />

                <Text style={[styles.formLabel, { marginTop: 16 }]}>Mobile number</Text>
                <View style={styles.phoneRow}>
                  <View style={styles.phonePrefixBox}>
                    <Text style={styles.phonePrefixText}>+91</Text>
                  </View>
                  <TextInput
                    style={[styles.input, styles.phoneInput]}
                    placeholder="10-digit number"
                    placeholderTextColor={COLORS.textFaint}
                    value={patientPhone}
                    onChangeText={setPatientPhone}
                    keyboardType="phone-pad"
                    maxLength={10}
                    returnKeyType="next"
                  />
                </View>

                <Text style={[styles.formLabel, { marginTop: 16 }]}>Symptoms summary</Text>
                <TextInput
                  style={[styles.input, styles.textArea]}
                  placeholder="Briefly describe the patient's main symptoms (max 200 characters)"
                  placeholderTextColor={COLORS.textFaint}
                  value={symptoms}
                  onChangeText={(t) => setSymptoms(t.slice(0, 200))}
                  multiline
                  numberOfLines={4}
                  textAlignVertical="top"
                  returnKeyType="done"
                />
                <Text style={styles.charCount}>{symptoms.length}/200</Text>
              </Animated.View>

              {error ? (
                <Animated.View entering={FadeInDown.duration(200)} style={styles.errorBanner}>
                  <Text style={styles.errorText}>{error}</Text>
                </Animated.View>
              ) : null}

              <Animated.View entering={FadeInDown.duration(280).delay(120)}>
                <TouchableOpacity
                  style={[styles.bookBtn, loading && styles.bookBtnDisabled]}
                  onPress={handleBook}
                  disabled={loading}
                  activeOpacity={0.82}
                >
                  {loading ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.bookBtnText}>Book appointment</Text>
                  )}
                </TouchableOpacity>
              </Animated.View>
            </>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.parchment },

  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 20, paddingVertical: 14,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
    gap: 12,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: COLORS.parchment,
    borderWidth: 1, borderColor: COLORS.border,
  },
  backArrow:    { fontSize: 18, color: COLORS.ink, marginTop: -1 },
  headerTitle:  { ...TYPE.titleLarge, color: COLORS.ink, flex: 1 },
  headerSpacer: { width: 36 },

  scroll: { padding: 20, gap: 16 },

  doctorCard: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.border,
    padding: 16, gap: 12,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05, shadowRadius: 6, elevation: 2,
  },
  doctorCardTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  doctorAvatar:  {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center',
  },
  doctorAvatarText: { fontSize: 20, fontWeight: '800', color: COLORS.parchment },
  doctorName:       { ...TYPE.titleLarge, color: COLORS.ink, marginBottom: 2 },
  doctorSpecialty:  { ...TYPE.bodyMed, color: COLORS.textMuted },
  platformBadge:    {
    paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: 'rgba(26,111,168,0.08)',
    borderRadius: RADIUS.pill, borderWidth: 1, borderColor: 'rgba(26,111,168,0.2)',
  },
  platformBadgeText:{ fontSize: 10, fontWeight: '700', color: '#1A6FA8', letterSpacing: 0.4 },
  doctorCardTime:   { flexDirection: 'row', alignItems: 'center', gap: 6 },
  timeIcon:         { fontSize: 14, color: COLORS.textMuted },
  timeText:         { ...TYPE.bodyMed, color: COLORS.textSub, fontWeight: '600' },

  formSection: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.border,
    padding: 16,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
  },
  formLabel: { ...TYPE.titleMed, color: COLORS.ink, marginBottom: 8 },

  input: {
    backgroundColor: COLORS.parchment,
    borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.border,
    paddingHorizontal: 14, paddingVertical: 12,
    fontSize: 15, color: COLORS.ink,
  },

  phoneRow:       { flexDirection: 'row', gap: 8 },
  phonePrefixBox: {
    paddingHorizontal: 14, paddingVertical: 12,
    backgroundColor: COLORS.parchment, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border,
    justifyContent: 'center',
  },
  phonePrefixText:{ fontSize: 15, fontWeight: '600', color: COLORS.ink },
  phoneInput:     { flex: 1 },

  textArea:   { minHeight: 96, paddingTop: 12 },
  charCount:  { ...TYPE.micro, color: COLORS.textFaint, textAlign: 'right', marginTop: 4 },

  errorBanner: {
    backgroundColor: COLORS.crimsonGhost, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: 'rgba(194,59,34,0.2)',
    paddingHorizontal: 14, paddingVertical: 10,
  },
  errorText: { ...TYPE.bodyMed, color: COLORS.crimson },

  bookBtn: {
    backgroundColor: COLORS.ink, borderRadius: RADIUS.lg,
    paddingVertical: 16, alignItems: 'center',
  },
  bookBtnDisabled: { opacity: 0.55 },
  bookBtnText: { ...TYPE.titleLarge, color: '#fff' },
});
