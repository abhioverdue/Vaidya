/**
 * Vaidya — ASHA Worker Self-Registration Screen
 * Submits to POST /asha/register
 * Demo fallback: pre-fills Tamil Nadu data and shows success immediately
 */

import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  TextInput, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as Location from 'expo-location';

import { COLORS, TYPE, RADIUS } from '@/constants';
import { apiClient } from '@/services/api';
import { markDemoMode } from '@/services/demoData';

// ── District codes ────────────────────────────────────────────────────────────

const DISTRICT_OPTIONS = [
  { code: 'TN-CBE', label: 'Coimbatore, TN'  },
  { code: 'TN-MDS', label: 'Madurai, TN'      },
  { code: 'TN-CHN', label: 'Chennai, TN'      },
  { code: 'MH-PNE', label: 'Pune, MH'         },
  { code: 'UP-LKW', label: 'Lucknow, UP'      },
];

// ── Success card ──────────────────────────────────────────────────────────────

function SuccessCard({ workerId }: { workerId: string }) {
  return (
    <Animated.View entering={FadeInDown.duration(320)} style={succ.wrap}>
      <View style={succ.iconRow}>
        <View style={succ.checkCircle}>
          <Text style={succ.checkText}>✓</Text>
        </View>
      </View>
      <Text style={succ.title}>Registration Successful</Text>
      <Text style={succ.sub}>
        You are now registered as an ASHA Worker on Vaidya.
      </Text>

      <View style={succ.idCard}>
        <Text style={succ.idLabel}>Your ASHA Worker ID</Text>
        <Text style={succ.idValue}>{workerId}</Text>
      </View>

      <View style={succ.instructionsCard}>
        <Text style={succ.instructionsTitle}>Next steps</Text>
        <Text style={succ.instructionItem}>1. Share your Worker ID with your district supervisor.</Text>
        <Text style={succ.instructionItem}>2. Your supervisor will activate your account within 24 hours.</Text>
        <Text style={succ.instructionItem}>3. Once activated, you can access the ASHA dashboard.</Text>
      </View>

      <TouchableOpacity
        style={succ.doneBtn}
        onPress={() => router.back()}
        activeOpacity={0.82}
      >
        <Text style={succ.doneBtnText}>Done</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const succ = StyleSheet.create({
  wrap:         { gap: 14, alignItems: 'center', paddingVertical: 8 },
  iconRow:      { marginBottom: 4 },
  checkCircle:  {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: COLORS.sageGhost, borderWidth: 2, borderColor: COLORS.sage,
    alignItems: 'center', justifyContent: 'center',
  },
  checkText:    { fontSize: 28, color: COLORS.sage, fontWeight: '700' },
  title:        { ...TYPE.headlineLarge, color: COLORS.ink, textAlign: 'center' },
  sub:          { ...TYPE.bodyMed, color: COLORS.textMuted, textAlign: 'center' },
  idCard:       {
    width: '100%', backgroundColor: COLORS.sageGhost,
    borderRadius: RADIUS.lg, borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)',
    paddingVertical: 16, paddingHorizontal: 20, alignItems: 'center', gap: 6,
  },
  idLabel:      { ...TYPE.bodyMed, color: COLORS.sage },
  idValue:      { fontSize: 24, fontWeight: '800', color: COLORS.sage, letterSpacing: 1.2 },
  instructionsCard: {
    width: '100%', backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border,
    padding: 16, gap: 8,
  },
  instructionsTitle: { ...TYPE.titleMed, color: COLORS.ink, marginBottom: 4 },
  instructionItem:   { ...TYPE.bodyMed, color: COLORS.textSub, lineHeight: 22 },
  doneBtn:      {
    width: '100%', backgroundColor: COLORS.ink,
    borderRadius: RADIUS.lg, paddingVertical: 16, alignItems: 'center', marginTop: 4,
  },
  doneBtnText:  { ...TYPE.titleLarge, color: '#fff' },
});

// ── Field component ───────────────────────────────────────────────────────────

function Field({
  label, value, onChangeText, placeholder,
  keyboardType, autoCapitalize, maxLength, optional,
}: {
  label: string; value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
  keyboardType?: 'default' | 'phone-pad' | 'numeric';
  autoCapitalize?: 'none' | 'words' | 'sentences';
  maxLength?: number;
  optional?: boolean;
}) {
  return (
    <View style={field.wrap}>
      <View style={field.labelRow}>
        <Text style={field.label}>{label}</Text>
        {optional && <Text style={field.optional}>optional</Text>}
      </View>
      <TextInput
        style={field.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={COLORS.textFaint}
        keyboardType={keyboardType ?? 'default'}
        autoCapitalize={autoCapitalize ?? 'sentences'}
        maxLength={maxLength}
        returnKeyType="next"
      />
    </View>
  );
}

const field = StyleSheet.create({
  wrap:     { gap: 6 },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  label:    { ...TYPE.titleMed, color: COLORS.ink },
  optional: { ...TYPE.micro, color: COLORS.textFaint, fontStyle: 'italic' },
  input:    {
    backgroundColor: COLORS.parchment,
    borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.border,
    paddingHorizontal: 14, paddingVertical: 12,
    fontSize: 15, color: COLORS.ink,
  },
});

// ── District picker ───────────────────────────────────────────────────────────

function DistrictPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <View style={dp.wrap}>
      <Text style={dp.label}>District code</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={dp.scroll}>
        <View style={dp.row}>
          {DISTRICT_OPTIONS.map((d) => {
            const active = value === d.code;
            return (
              <TouchableOpacity
                key={d.code}
                style={[dp.chip, active && dp.chipActive]}
                onPress={() => onChange(d.code)}
                activeOpacity={0.75}
              >
                <Text style={[dp.chipCode, active && dp.chipCodeActive]}>{d.code}</Text>
                <Text style={[dp.chipLabel, active && dp.chipLabelActive]}>{d.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}

const dp = StyleSheet.create({
  wrap:          { gap: 8 },
  label:         { ...TYPE.titleMed, color: COLORS.ink },
  scroll:        { marginHorizontal: -20 },
  row:           { flexDirection: 'row', gap: 8, paddingHorizontal: 20, paddingBottom: 2 },
  chip:          {
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: COLORS.surface, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border, gap: 2,
  },
  chipActive:    { backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  chipCode:      { fontSize: 11, fontWeight: '700', color: COLORS.ink },
  chipCodeActive:{ color: '#fff' },
  chipLabel:     { ...TYPE.micro, color: COLORS.textMuted },
  chipLabelActive:{ color: 'rgba(255,255,255,0.7)' },
});

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function AshaRegisterScreen() {
  const [fullName,      setFullName]      = useState('');
  const [mobile,        setMobile]        = useState('');
  const [nhmId,         setNhmId]         = useState('');
  const [village,       setVillage]       = useState('');
  const [districtCode,  setDistrictCode]  = useState('TN-CBE');
  const [state,         setState]         = useState('');
  const [lat,           setLat]           = useState('');
  const [lng,           setLng]           = useState('');
  const [locLoading,    setLocLoading]    = useState(false);
  const [locError,      setLocError]      = useState<string | null>(null);
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState<string | null>(null);
  const [workerId,      setWorkerId]      = useState<string | null>(null);

  async function handleGetLocation() {
    setLocLoading(true);
    setLocError(null);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setLocError('Location permission denied. Enter coordinates manually.');
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setLat(pos.coords.latitude.toFixed(6));
      setLng(pos.coords.longitude.toFixed(6));
    } catch {
      setLocError('Could not get location. Enter coordinates manually.');
    } finally {
      setLocLoading(false);
    }
  }

  function prefillDemo() {
    setFullName('Meena Devi');
    setMobile('9876543210');
    setNhmId('TN-ASHA-00142');
    setVillage('Maduranthakam');
    setDistrictCode('TN-CBE');
    setState('Tamil Nadu');
    setLat('11.0168');
    setLng('77.0094');
  }

  async function handleRegister() {
    if (!fullName.trim())  { setError('Please enter your full name.'); return; }
    if (!mobile.trim() || mobile.trim().length < 10) { setError('Please enter a valid 10-digit mobile number.'); return; }
    if (!village.trim())   { setError('Please enter your village name.'); return; }
    if (!state.trim())     { setError('Please enter your state.'); return; }
    setError(null);
    setLoading(true);

    const payload = {
      full_name:     fullName.trim(),
      mobile_number: `+91${mobile.trim().replace(/^(\+91|0)/, '')}`,
      nhm_id:        nhmId.trim() || undefined,
      village_name:  village.trim(),
      district_code: districtCode,
      state:         state.trim(),
      latitude:      lat ? parseFloat(lat) : undefined,
      longitude:     lng ? parseFloat(lng) : undefined,
    };

    try {
      const { data } = await apiClient.post('/asha/register', payload);
      setWorkerId(data.worker_id);
    } catch {
      markDemoMode();
      await new Promise((r) => setTimeout(r, 1000));
      setWorkerId(`ASHA-TN-${Math.floor(10000 + Math.random() * 90000)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backArrow}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Register as ASHA Worker</Text>
        <View style={styles.headerSpacer} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {workerId ? (
            <SuccessCard workerId={workerId} />
          ) : (
            <>
              {/* Demo prefill banner */}
              <Animated.View entering={FadeInDown.duration(260)}>
                <TouchableOpacity style={styles.demoBanner} onPress={prefillDemo} activeOpacity={0.8}>
                  <Text style={styles.demoBannerText}>
                    Tap to pre-fill with Tamil Nadu demo data
                  </Text>
                </TouchableOpacity>
              </Animated.View>

              {/* Personal details */}
              <Animated.View entering={FadeInDown.duration(280).delay(40)} style={styles.card}>
                <Text style={styles.cardTitle}>Personal Details</Text>
                <View style={styles.cardFields}>
                  <Field label="Full name" value={fullName} onChangeText={setFullName} placeholder="As on Aadhaar" autoCapitalize="words" />
                  <View style={styles.phoneFieldWrap}>
                    <Text style={field.label}>Mobile number</Text>
                    <View style={styles.phoneRow}>
                      <View style={styles.phonePrefixBox}>
                        <Text style={styles.phonePrefixText}>+91</Text>
                      </View>
                      <TextInput
                        style={[field.input, { flex: 1 }]}
                        value={mobile}
                        onChangeText={setMobile}
                        placeholder="10-digit number"
                        placeholderTextColor={COLORS.textFaint}
                        keyboardType="phone-pad"
                        maxLength={10}
                      />
                    </View>
                  </View>
                  <Field label="NHM ID" value={nhmId} onChangeText={setNhmId} placeholder="e.g. TN-ASHA-00142" optional autoCapitalize="none" />
                </View>
              </Animated.View>

              {/* Location details */}
              <Animated.View entering={FadeInDown.duration(280).delay(80)} style={styles.card}>
                <Text style={styles.cardTitle}>Location Details</Text>
                <View style={styles.cardFields}>
                  <Field label="Village name" value={village} onChangeText={setVillage} placeholder="Your village / habitation" autoCapitalize="words" />
                  <DistrictPicker value={districtCode} onChange={setDistrictCode} />
                  <Field label="State" value={state} onChangeText={setState} placeholder="e.g. Tamil Nadu" autoCapitalize="words" />
                </View>
              </Animated.View>

              {/* GPS location */}
              <Animated.View entering={FadeInDown.duration(280).delay(120)} style={styles.card}>
                <Text style={styles.cardTitle}>GPS Location</Text>
                <Text style={styles.cardSub}>Used to match patients in your area</Text>
                <TouchableOpacity
                  style={styles.locationBtn}
                  onPress={handleGetLocation}
                  disabled={locLoading}
                  activeOpacity={0.8}
                >
                  {locLoading ? (
                    <ActivityIndicator size="small" color={COLORS.sage} />
                  ) : (
                    <Text style={styles.locationBtnText}>
                      {lat && lng ? 'Location captured — tap to refresh' : 'Use current location'}
                    </Text>
                  )}
                </TouchableOpacity>
                {locError ? <Text style={styles.locErrorText}>{locError}</Text> : null}
                {(lat || lng) && (
                  <Text style={styles.coordsText}>
                    Lat: {lat}  Lng: {lng}
                  </Text>
                )}
                <View style={styles.manualCoordRow}>
                  <View style={{ flex: 1 }}>
                    <TextInput
                      style={field.input}
                      value={lat}
                      onChangeText={setLat}
                      placeholder="Latitude"
                      placeholderTextColor={COLORS.textFaint}
                      keyboardType="numeric"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <TextInput
                      style={field.input}
                      value={lng}
                      onChangeText={setLng}
                      placeholder="Longitude"
                      placeholderTextColor={COLORS.textFaint}
                      keyboardType="numeric"
                    />
                  </View>
                </View>
              </Animated.View>

              {/* Error */}
              {error ? (
                <Animated.View entering={FadeInDown.duration(200)} style={styles.errorBanner}>
                  <Text style={styles.errorText}>{error}</Text>
                </Animated.View>
              ) : null}

              {/* Submit */}
              <Animated.View entering={FadeInDown.duration(280).delay(160)}>
                <TouchableOpacity
                  style={[styles.registerBtn, loading && styles.registerBtnDisabled]}
                  onPress={handleRegister}
                  disabled={loading}
                  activeOpacity={0.82}
                >
                  {loading ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.registerBtnText}>Register</Text>
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
    backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border,
  },
  backArrow:    { fontSize: 18, color: COLORS.ink, marginTop: -1 },
  headerTitle:  { ...TYPE.titleLarge, color: COLORS.ink, flex: 1 },
  headerSpacer: { width: 36 },

  scroll: { padding: 20, gap: 16 },

  demoBanner: {
    backgroundColor: COLORS.goldGhost, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: 'rgba(154,107,31,0.25)',
    paddingVertical: 10, paddingHorizontal: 14, alignItems: 'center',
  },
  demoBannerText: { ...TYPE.bodyMed, color: COLORS.gold, fontWeight: '600' },

  card: {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 16, gap: 12,
    shadowColor: COLORS.ink, shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
  },
  cardTitle: { ...TYPE.titleLarge, color: COLORS.ink },
  cardSub:   { ...TYPE.bodyMed, color: COLORS.textMuted, marginTop: -6 },
  cardFields:{ gap: 14 },

  phoneFieldWrap: { gap: 6 },
  phoneRow:       { flexDirection: 'row', gap: 8 },
  phonePrefixBox: {
    paddingHorizontal: 14, paddingVertical: 12,
    backgroundColor: COLORS.parchment, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border, justifyContent: 'center',
  },
  phonePrefixText:{ fontSize: 15, fontWeight: '600', color: COLORS.ink },

  locationBtn: {
    backgroundColor: COLORS.sageGhost,
    borderRadius: RADIUS.md, borderWidth: 1, borderColor: 'rgba(58,95,82,0.2)',
    paddingVertical: 12, alignItems: 'center',
  },
  locationBtnText: { ...TYPE.titleMed, color: COLORS.sage },
  locErrorText:    { ...TYPE.bodyMed, color: COLORS.crimson },
  coordsText:      { ...TYPE.micro, color: COLORS.sage, fontWeight: '600' },
  manualCoordRow:  { flexDirection: 'row', gap: 8 },

  errorBanner: {
    backgroundColor: COLORS.crimsonGhost, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: 'rgba(194,59,34,0.2)',
    paddingHorizontal: 14, paddingVertical: 10,
  },
  errorText: { ...TYPE.bodyMed, color: COLORS.crimson },

  registerBtn: {
    backgroundColor: COLORS.ink, borderRadius: RADIUS.lg,
    paddingVertical: 16, alignItems: 'center',
  },
  registerBtnDisabled: { opacity: 0.55 },
  registerBtnText:     { ...TYPE.titleLarge, color: '#fff' },
});
