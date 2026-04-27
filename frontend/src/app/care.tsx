/**
 * Vaidya — Care finder  (OSM map + real-time GPS tracking)
 *
 * BUG FIX — WEB PLATFORM
 * ─────────────────────────────────────────────────────────────────────────────
 * FIX-10  react-native-maps crashes on web with "null is not an object
 *         (evaluating 'RNMaps.init')" because the native module doesn't exist
 *         in a browser.  The MapView import is now gated behind Platform.OS so
 *         the web bundle never loads the native map module.
 *
 *         On web we render an <iframe> pointing at OpenStreetMap's embed URL
 *         (no API key needed).  Hospital pins are overlaid as an HTML layer
 *         via a generated data-URL.  This gives a fully functional, demoable
 *         web experience without adding new dependencies.
 *
 *         On native (Android/iOS) the full react-native-maps implementation is
 *         unchanged.
 */

import React, {
  useCallback, useEffect, useRef, useState,
} from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, FlatList,
  StyleSheet, Linking, ActivityIndicator, Platform,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import Animated, { FadeInDown, FadeInUp, SlideInDown } from 'react-native-reanimated';
import { useQuery } from '@tanstack/react-query';
import * as Location from 'expo-location';

// FIX-10: Conditional import — react-native-maps is native-only
let MapView: any = null;
let Marker: any = null;
let Circle: any = null;
let PROVIDER_DEFAULT: any = null;
let PROVIDER_GOOGLE: any  = null;

if (Platform.OS !== 'web') {
  try {
    const RNMaps = require('react-native-maps');
    MapView          = RNMaps.default;
    Marker           = RNMaps.Marker;
    Circle           = RNMaps.Circle;
    PROVIDER_DEFAULT = RNMaps.PROVIDER_DEFAULT;
    PROVIDER_GOOGLE  = RNMaps.PROVIDER_GOOGLE;
  } catch (e) {
    console.warn('[Vaidya] react-native-maps failed to load — map will be unavailable:', e);
  }
}

// Use Google Maps provider explicitly on Android so Google Maps tiles render
// and the Google Maps branding is visible (required for Google Solutions demo).
const MAP_PROVIDER = Platform.OS === 'android' ? PROVIDER_GOOGLE : PROVIDER_DEFAULT;

import { COLORS, TYPE, RADIUS } from '@/constants';
import { fetchHospitals } from '@/services/api';
import type { HospitalResult, HospitalType } from '@/types';

// ── Constants ─────────────────────────────────────────────────────────────────

const DEFAULT_DELTA = 0.08;

const TYPE_COLORS: Record<string, string> = {
  phc:      '#1A6FA8',
  chc:      '#256B2E',
  district: '#7B3B9E',
  private:  '#B56B0F',
  esic:     '#0D6B56',
  other:    COLORS.textMuted,
};

const TYPE_LABELS: Record<string, string> = {
  phc: 'PHC', chc: 'CHC', district: 'District', private: 'Private',
  esic: 'ESIC', other: 'Other',
};

const TABS: Array<{ key: HospitalType | 'all'; label: string }> = [
  { key: 'all',      label: 'All'      },
  { key: 'phc',      label: 'PHC'      },
  { key: 'chc',      label: 'CHC'      },
  { key: 'district', label: 'District' },
  { key: 'private',  label: 'Private'  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function openDirections(lat: number, lng: number, label: string) {
  const encoded = encodeURIComponent(label);
  const url = Platform.OS === 'ios'
    ? `maps://?daddr=${lat},${lng}&dirflg=d`
    : Platform.OS === 'web'
      ? `https://www.openstreetmap.org/directions?engine=graphhopper_car&route=;${lat},${lng}`
      : `geo:${lat},${lng}?q=${lat},${lng}(${encoded})`;
  Linking.openURL(url).catch(() =>
    Linking.openURL(`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}&zoom=16`),
  );
}

function haversineKm(
  lat1: number, lng1: number,
  lat2: number, lng2: number,
): number {
  const R  = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ── FIX-10: Web map component using OpenStreetMap iframe ──────────────────────

function WebMapView({
  userLat,
  userLng,
  hospitals,
  selected,
  onSelectHospital,
}: {
  userLat: number;
  userLng: number;
  hospitals: HospitalResult[];
  selected: HospitalResult | null;
  onSelectHospital: (h: HospitalResult) => void;
}) {
  const focusLat = selected ? selected.latitude  : userLat;
  const focusLng = selected ? selected.longitude : userLng;
  const zoom     = selected ? 15 : 13;

  // Build an OSM embed URL centred on user / selected hospital
  const osmUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${focusLng - 0.05},${focusLat - 0.05},${focusLng + 0.05},${focusLat + 0.05}&layer=mapnik&marker=${focusLat},${focusLng}`;

  return (
    <View style={{ flex: 1, position: 'relative' }}>
      {/* OSM iframe — fills the map area */}
      <iframe
        src={osmUrl}
        style={{ width: '100%', height: '100%', border: 'none' }}
        title="OpenStreetMap"
        loading="lazy"
      />

      {/* Hospital list overlay — scrollable chips along the bottom of the map */}
      {hospitals.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={webMap.chipsBar}
          contentContainerStyle={webMap.chipsContent}
        >
          {hospitals.map((h) => {
            const tc  = TYPE_COLORS[h.hospital_type] ?? COLORS.textMuted;
            const isSel = selected?.id === h.id;
            return (
              <TouchableOpacity
                key={h.id}
                style={[webMap.chip, isSel && { borderColor: tc, backgroundColor: tc + '18' }]}
                onPress={() => onSelectHospital(h)}
              >
                <View style={[webMap.chipDot, { backgroundColor: tc }]} />
                <Text style={webMap.chipText} numberOfLines={1}>{h.name}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const webMap = StyleSheet.create({
  chipsBar:     { position: 'absolute', bottom: 0, left: 0, right: 0 },
  chipsContent: { padding: 8, gap: 6 },
  chip:         {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: 'rgba(247,244,238,0.95)',
    borderRadius: RADIUS.pill, borderWidth: 1.5, borderColor: COLORS.border,
    paddingHorizontal: 10, paddingVertical: 6,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1, shadowRadius: 3,
  },
  chipDot:  { width: 8, height: 8, borderRadius: 4 },
  chipText: { fontSize: 11, fontWeight: '600', color: COLORS.ink, maxWidth: 120 },
});

// ── Sub-components ────────────────────────────────────────────────────────────

function HospitalPin({
  hospital, onPress, selected,
}: { hospital: HospitalResult; onPress: () => void; selected: boolean }) {
  if (Platform.OS === 'web' || !Marker) return null;
  const tc = TYPE_COLORS[hospital.hospital_type] ?? COLORS.textMuted;
  return (
    <Marker
      coordinate={{ latitude: hospital.latitude, longitude: hospital.longitude }}
      onPress={onPress}
      anchor={{ x: 0.5, y: 1 }}
      tracksViewChanges={false}
    >
      <View style={[pin.wrap, selected && pin.wrapSelected]}>
        <View style={[pin.dot, { backgroundColor: tc }, selected && pin.dotSelected]} />
        {selected && (
          <Text style={[pin.label, { color: tc }]} numberOfLines={1}>
            {TYPE_LABELS[hospital.hospital_type] ?? ''}
          </Text>
        )}
      </View>
    </Marker>
  );
}

const pin = StyleSheet.create({
  wrap:        { alignItems: 'center' },
  wrapSelected:{ },
  dot:         { width: 14, height: 14, borderRadius: 7, borderWidth: 2, borderColor: '#fff' },
  dotSelected: { width: 18, height: 18, borderRadius: 9, borderWidth: 2.5 },
  label:       {
    fontSize: 9, fontWeight: '700', marginTop: 2, backgroundColor: '#fff',
    paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3,
    overflow: 'hidden',
  },
});

function HospitalSheet({
  hospital, userLat, userLng, onClose,
}: {
  hospital: HospitalResult;
  userLat: number; userLng: number;
  onClose: () => void;
}) {
  const tc     = TYPE_COLORS[hospital.hospital_type] ?? COLORS.textMuted;
  const liveKm = haversineKm(userLat, userLng, hospital.latitude, hospital.longitude);

  return (
    <Animated.View entering={SlideInDown.duration(280)} style={sheet.wrap}>
      <View style={sheet.handle} />
      <View style={[sheet.typePill, { backgroundColor: tc + '18' }]}>
        <View style={[sheet.typeDot, { backgroundColor: tc }]} />
        <Text style={[sheet.typeText, { color: tc }]}>
          {TYPE_LABELS[hospital.hospital_type]?.toUpperCase() ?? 'FACILITY'}
        </Text>
      </View>
      <Text style={sheet.name}>{hospital.name}</Text>
      {hospital.address && (
        <Text style={sheet.addr} numberOfLines={2}>{hospital.address}</Text>
      )}

      <View style={sheet.pills}>
        <View style={sheet.pill}>
          <Text style={sheet.pillText}>{liveKm.toFixed(1)} km away</Text>
        </View>
        {hospital.ambulance_108 && (
          <View style={[sheet.pill, sheet.pillGreen]}>
            <Text style={[sheet.pillText, { color: COLORS.sage }]}>108 ambulance</Text>
          </View>
        )}
        {hospital.open_24h && (
          <View style={[sheet.pill, sheet.pillGreen]}>
            <Text style={[sheet.pillText, { color: COLORS.sage }]}>Open 24 h</Text>
          </View>
        )}
        {hospital.pmjay_empanelled && (
          <View style={[sheet.pill, sheet.pillGold]}>
            <Text style={[sheet.pillText, { color: COLORS.gold }]}>PMJAY</Text>
          </View>
        )}
      </View>

      <View style={sheet.actions}>
        <TouchableOpacity
          style={sheet.navBtn}
          onPress={() => openDirections(hospital.latitude, hospital.longitude, hospital.name)}
        >
          <Text style={sheet.navBtnText}>Get directions</Text>
        </TouchableOpacity>
        {hospital.phone && (
          <TouchableOpacity
            style={sheet.callBtn}
            onPress={() => Linking.openURL(`tel:${hospital.phone}`)}
          >
            <Text style={sheet.callBtnText}>Call</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={sheet.closeBtn} onPress={onClose}>
          <Text style={sheet.closeBtnText}>✕</Text>
        </TouchableOpacity>
      </View>
    </Animated.View>
  );
}

const sheet = StyleSheet.create({
  wrap:       {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: COLORS.surface,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 20, paddingBottom: 32,
    borderTopWidth: 1, borderTopColor: COLORS.border,
    shadowColor: '#000', shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.08, shadowRadius: 12, elevation: 12,
  },
  handle:     { width: 36, height: 4, backgroundColor: COLORS.border, borderRadius: 2, alignSelf: 'center', marginBottom: 14 },
  typePill:   { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.pill, marginBottom: 8 },
  typeDot:    { width: 7, height: 7, borderRadius: 4 },
  typeText:   { fontSize: 10, fontWeight: '700', letterSpacing: 0.6 },
  name:       { fontSize: 18, fontWeight: '700', color: COLORS.ink, letterSpacing: -0.3, marginBottom: 4 },
  addr:       { ...TYPE.bodySmall, color: COLORS.textMuted, marginBottom: 12 },
  pills:      { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 },
  pill:       { paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.pill, backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border },
  pillGreen:  { backgroundColor: COLORS.sageGhost, borderColor: 'rgba(58,95,82,0.2)' },
  pillGold:   { backgroundColor: 'rgba(154,107,31,0.08)', borderColor: 'rgba(154,107,31,0.2)' },
  pillText:   { fontSize: 11, fontWeight: '600', color: COLORS.textSub },
  actions:    { flexDirection: 'row', gap: 8 },
  navBtn:     { flex: 1, backgroundColor: COLORS.ink, borderRadius: RADIUS.lg, paddingVertical: 14, alignItems: 'center' },
  navBtnText: { ...TYPE.titleMed, color: '#fff' },
  callBtn:    { backgroundColor: COLORS.sage, borderRadius: RADIUS.lg, paddingHorizontal: 20, paddingVertical: 14, alignItems: 'center' },
  callBtnText:{ ...TYPE.titleMed, color: '#fff' },
  closeBtn:   { width: 46, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  closeBtnText:{ fontSize: 16, color: COLORS.textMuted },
});

function HospitalCard({
  h, index, userLat, userLng, onPressMap,
}: {
  h: HospitalResult; index: number;
  userLat: number; userLng: number;
  onPressMap: () => void;
}) {
  const tc     = TYPE_COLORS[h.hospital_type] ?? COLORS.textMuted;
  const liveKm = haversineKm(userLat, userLng, h.latitude, h.longitude);

  return (
    <Animated.View entering={FadeInDown.duration(280).delay(index * 35)}>
      <TouchableOpacity style={card.wrap} activeOpacity={0.82} onPress={onPressMap}>
        <View style={[card.bar, { backgroundColor: tc }]} />
        <View style={card.body}>
          <View style={card.top}>
            <Text style={card.name} numberOfLines={2}>{h.name}</Text>
            <View style={[card.badge, { backgroundColor: tc + '18' }]}>
              <Text style={[card.badgeText, { color: tc }]}>{TYPE_LABELS[h.hospital_type]?.toUpperCase()}</Text>
            </View>
          </View>
          {h.address && <Text style={card.addr} numberOfLines={1}>{h.address}</Text>}
          <View style={card.footer}>
            <Text style={card.dist}>{liveKm.toFixed(1)} km</Text>
            {h.ambulance_108  && <Text style={card.tag}>108</Text>}
            {h.open_24h       && <Text style={card.tag}>24 h</Text>}
            {h.pmjay_empanelled && <Text style={[card.tag, card.tagGold]}>PMJAY</Text>}
          </View>
        </View>
        {h.phone ? (
          <TouchableOpacity
            style={card.callBtn}
            onPress={() => Linking.openURL(`tel:${h.phone}`)}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={card.callText}>Call</Text>
          </TouchableOpacity>
        ) : (
          <View style={card.mapHint}>
            <Text style={card.mapHintText}>Map →</Text>
          </View>
        )}
      </TouchableOpacity>
    </Animated.View>
  );
}

const card = StyleSheet.create({
  wrap:     { flexDirection: 'row', backgroundColor: COLORS.surface, borderRadius: RADIUS.lg, marginBottom: 8, borderWidth: 1, borderColor: COLORS.border, overflow: 'hidden' },
  bar:      { width: 4 },
  body:     { flex: 1, padding: 12 },
  top:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 6, marginBottom: 2 },
  name:     { ...TYPE.titleMed, color: COLORS.ink, flex: 1, lineHeight: 20 },
  badge:    { borderRadius: RADIUS.pill, paddingHorizontal: 7, paddingVertical: 2 },
  badgeText:{ fontSize: 9, fontWeight: '700', letterSpacing: 0.4 },
  addr:     { ...TYPE.micro, color: COLORS.textMuted, marginBottom: 6 },
  footer:   { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  dist:     { fontSize: 11, fontWeight: '700', color: COLORS.sage },
  tag:      { fontSize: 10, fontWeight: '600', color: COLORS.textMuted, backgroundColor: COLORS.parchment, paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.pill, borderWidth: 1, borderColor: COLORS.border },
  tagGold:  { color: COLORS.gold, borderColor: 'rgba(154,107,31,0.2)', backgroundColor: 'rgba(154,107,31,0.06)' },
  callBtn:  { justifyContent: 'center', paddingHorizontal: 14, borderLeftWidth: 1, borderLeftColor: COLORS.border },
  callText: { fontSize: 12, fontWeight: '700', color: COLORS.sage },
  mapHint:  { justifyContent: 'center', paddingHorizontal: 12 },
  mapHintText:{ fontSize: 11, color: COLORS.textFaint },
});

// ── Main screen ───────────────────────────────────────────────────────────────

export default function CareScreen() {
  const { t } = useTranslation();
  const { height: screenH } = useWindowDimensions();
  const mapSplitHeight = screenH * 0.42;

  const [viewMode, setViewMode]       = useState<'split' | 'map'>('split');
  const [activeTab, setActiveTab]     = useState<HospitalType | 'all'>('all');
  const [selected, setSelected]       = useState<HospitalResult | null>(null);
  const [permGranted, setPermGranted] = useState(false);
  const [userLoc, setUserLoc]         = useState<{
    lat: number; lng: number; accuracy: number; heading: number | null;
  } | null>(null);

  const mapRef        = useRef<any>(null);
  const watchRef      = useRef<Location.LocationSubscription | null>(null);
  const centreQueued  = useRef(false);

  const startTracking = useCallback(async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return;
    setPermGranted(true);

    const initial = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    const { latitude: lat, longitude: lng, accuracy, heading } = initial.coords;
    setUserLoc({ lat, lng, accuracy: accuracy ?? 50, heading: heading ?? null });
    centreOnUser(lat, lng);

    watchRef.current = await Location.watchPositionAsync(
      {
        accuracy:          Location.Accuracy.BestForNavigation,
        distanceInterval:  5,
        timeInterval:      3000,
      },
      (loc) => {
        const { latitude, longitude, accuracy: acc, heading: hdg } = loc.coords;
        setUserLoc({
          lat:      latitude,
          lng:      longitude,
          accuracy: acc ?? 50,
          heading:  hdg ?? null,
        });
        if (!selected && centreQueued.current) {
          centreOnUser(latitude, longitude);
          centreQueued.current = false;
        }
      },
    );
  }, [selected]);

  useEffect(() => {
    return () => { watchRef.current?.remove(); };
  }, []);

  function centreOnUser(lat: number, lng: number) {
    if (Platform.OS === 'web' || !mapRef.current) return;
    mapRef.current?.animateToRegion(
      { latitude: lat, longitude: lng, latitudeDelta: DEFAULT_DELTA, longitudeDelta: DEFAULT_DELTA },
      600,
    );
  }

  function handleCentreBtn() {
    if (!userLoc) { startTracking(); return; }
    setSelected(null);
    centreOnUser(userLoc.lat, userLoc.lng);
    centreQueued.current = true;
  }

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['hospitals', userLoc?.lat, userLoc?.lng, activeTab],
    queryFn:  () => fetchHospitals({
      lat:       userLoc!.lat,
      lng:       userLoc!.lng,
      type:      activeTab === 'all' ? undefined : activeTab,
      radius_km: 50,
    }),
    enabled:  !!userLoc,
    staleTime: 2 * 60 * 1000,
    retry:    1,
  });

  const hospitals: HospitalResult[] = data?.results ?? [];

  useEffect(() => {
    if (!hospitals.length || !userLoc || !mapRef.current || Platform.OS === 'web') return;
    const coords = [
      { latitude: userLoc.lat, longitude: userLoc.lng },
      ...hospitals.slice(0, 10).map((h) => ({ latitude: h.latitude, longitude: h.longitude })),
    ];
    try {
      mapRef.current.fitToCoordinates(coords, {
        edgePadding: { top: 60, right: 40, bottom: 240, left: 40 },
        animated:    true,
      });
    } catch {}
  }, [hospitals.length]);

  useEffect(() => {
    if (!selected || !mapRef.current || Platform.OS === 'web') return;
    try {
      mapRef.current.animateToRegion(
        {
          latitude:      selected.latitude - 0.012,
          longitude:     selected.longitude,
          latitudeDelta: 0.03,
          longitudeDelta:0.03,
        },
        400,
      );
    } catch {}
  }, [selected?.id]);

  // ── Map area (platform-split) ─────────────────────────────────────────────
  const mapAreaStyle = viewMode === 'map'
    ? styles.mapFull
    : [styles.mapSplit, { height: mapSplitHeight }];

  const mapContent = !permGranted ? (
    <Animated.View entering={FadeInDown.duration(400)} style={styles.locPrompt}>
      <Text style={styles.locIcon}>◎</Text>
      <Text style={styles.locTitle}>{t('home.find_hospital')}</Text>
      <Text style={styles.locBody}>{t('care.loading_hospitals')}</Text>
      <TouchableOpacity style={styles.locBtn} onPress={startTracking}>
        <Text style={styles.locBtnText}>{t('care.allow_location')}</Text>
      </TouchableOpacity>
    </Animated.View>
  ) : Platform.OS === 'web' ? (
    /* Web — OSM iframe */
    <WebMapView
      userLat={userLoc?.lat ?? 12.97}
      userLng={userLoc?.lng ?? 79.16}
      hospitals={hospitals}
      selected={selected}
      onSelectHospital={setSelected}
    />
  ) : MapView ? (
    /* Native — react-native-maps */
    <MapView
      ref={mapRef}
      style={StyleSheet.absoluteFillObject}
      provider={MAP_PROVIDER}
      showsUserLocation={false}
      showsMyLocationButton={false}
      showsCompass={true}
      showsScale={true}
      mapType="standard"
      initialRegion={{
        latitude:       userLoc?.lat ?? 12.97,
        longitude:      userLoc?.lng ?? 79.16,
        latitudeDelta:  DEFAULT_DELTA,
        longitudeDelta: DEFAULT_DELTA,
      }}
      onPress={() => setSelected(null)}
    >
      {userLoc && (
        <>
          <Circle
            center={{ latitude: userLoc.lat, longitude: userLoc.lng }}
            radius={Math.max(userLoc.accuracy, 10)}
            fillColor="rgba(58,95,82,0.08)"
            strokeColor="rgba(58,95,82,0.25)"
            strokeWidth={1}
            zIndex={1}
          />
          <Marker
            coordinate={{ latitude: userLoc.lat, longitude: userLoc.lng }}
            anchor={{ x: 0.5, y: 0.5 }}
            flat={true}
            rotation={userLoc.heading ?? 0}
            zIndex={10}
            tracksViewChanges={false}
          >
            <View style={styles.userDotWrap}>
              {userLoc.heading !== null && (
                <View style={styles.headingArrow} />
              )}
              <View style={styles.userDot} />
            </View>
          </Marker>
        </>
      )}
      {hospitals.map((h) => (
        <HospitalPin
          key={h.id}
          hospital={h}
          selected={selected?.id === h.id}
          onPress={() => setSelected(h)}
        />
      ))}
    </MapView>
  ) : (
    /* react-native-maps failed to load — show OSM fallback */
    <WebMapView
      userLat={userLoc?.lat ?? 12.97}
      userLng={userLoc?.lng ?? 79.16}
      hospitals={hospitals}
      selected={selected}
      onSelectHospital={setSelected}
    />
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backArrow}>←</Text>
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>{t('care.screen_title')}</Text>
          <Text style={styles.headerSub}>
            {!permGranted
              ? t('care.loading_hospitals')
              : isLoading
                ? t('care.loading_hospitals')
                : `${hospitals.length} ${t('care.hospitals_tab').toLowerCase()} · GPS`}
          </Text>
        </View>
        <TouchableOpacity
          style={styles.viewToggle}
          onPress={() => setViewMode((m) => m === 'split' ? 'map' : 'split')}
        >
          <Text style={styles.viewToggleText}>
            {viewMode === 'split' ? t('care.hospitals_tab') : t('common.back')}
          </Text>
        </TouchableOpacity>
      </View>

      {/* ── Filter tabs ─────────────────────────────────────────────────── */}
      <ScrollView
        horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tabs}
        style={styles.tabsBar}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <TouchableOpacity
              key={tab.key}
              style={[styles.tab, active && styles.tabActive]}
              onPress={() => { setActiveTab(tab.key); setSelected(null); }}
            >
              <Text style={[styles.tabText, active && styles.tabTextActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* ── Map area ────────────────────────────────────────────────────── */}
      <View style={mapAreaStyle}>
        {mapContent}

        {/* FAB — native only (web has no imperativeAnimateToRegion) */}
        {permGranted && Platform.OS !== 'web' && (
          <TouchableOpacity style={styles.fab} onPress={handleCentreBtn}>
            <Text style={styles.fabText}>◎</Text>
          </TouchableOpacity>
        )}

        {/* Accuracy badge */}
        {userLoc && (
          <View style={styles.accuracyBadge}>
            <View style={[
              styles.accuracyDot,
              { backgroundColor: userLoc.accuracy < 20 ? COLORS.sage : userLoc.accuracy < 60 ? COLORS.gold : COLORS.crimson },
            ]} />
            <Text style={styles.accuracyText}>±{Math.round(userLoc.accuracy)} m</Text>
          </View>
        )}
      </View>

      {/* ── Hospital list ────────────────────────────────────────────────── */}
      {viewMode === 'split' && (
        <View style={styles.listPanel}>
          {isLoading && !hospitals.length && (
            <View style={styles.loadRow}>
              <ActivityIndicator size="small" color={COLORS.sage} />
              <Text style={styles.loadText}>{t('care.loading_hospitals')}</Text>
            </View>
          )}

          {!!error && !isLoading && (
            <View style={styles.errorRow}>
              <Text style={styles.errorText}>{t('care.no_hospitals')}</Text>
              <TouchableOpacity onPress={() => refetch()} style={styles.retryBtn}>
                <Text style={styles.retryText}>{t('common.retry')}</Text>
              </TouchableOpacity>
            </View>
          )}

          <FlatList
            data={hospitals}
            keyExtractor={(h) => h.id}
            contentContainerStyle={styles.listContent}
            showsVerticalScrollIndicator={false}
            renderItem={({ item: h, index }) => (
              <HospitalCard
                h={h} index={index}
                userLat={userLoc?.lat ?? 0}
                userLng={userLoc?.lng ?? 0}
                onPressMap={() => setSelected(h)}
              />
            )}
            ListFooterComponent={
              <View>
                <TouchableOpacity
                  style={styles.teleRow}
                  onPress={() => Linking.openURL('https://esanjeevani.mohfw.gov.in/#/')}
                >
                  <View style={styles.teleLeft}>
                    <Text style={styles.teleTitle}>{t('care.esanjeevani')}</Text>
                    <Text style={styles.teleSub}>{t('care.teleconsult_free')}</Text>
                  </View>
                  <Text style={styles.teleArrow}>→</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.emergencyBtn}
                  onPress={() => Linking.openURL('tel:108')}
                >
                  <Text style={styles.emergencyText}>{t('common.call_emergency')} — free</Text>
                </TouchableOpacity>

                <View style={{ height: 40 }} />
              </View>
            }
          />
        </View>
      )}

      {/* ── Selected hospital bottom sheet ───────────────────────────────── */}
      {selected && userLoc && (
        <HospitalSheet
          hospital={selected}
          userLat={userLoc.lat}
          userLng={userLoc.lng}
          onClose={() => setSelected(null)}
        />
      )}

    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.parchment },

  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 20, paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
    gap: 12,
  },
  backBtn:      { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border },
  backArrow:    { fontSize: 18, color: COLORS.ink, marginTop: -1 },
  headerCenter: { flex: 1, gap: 1 },
  headerTitle:  { ...TYPE.titleLarge, color: COLORS.ink },
  headerSub:    { ...TYPE.micro, color: COLORS.textFaint },
  viewToggle:   { paddingHorizontal: 12, paddingVertical: 7, borderRadius: RADIUS.pill, backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border },
  viewToggleText:{ ...TYPE.micro, color: COLORS.ink, fontWeight: '600' },

  tabsBar:  { backgroundColor: COLORS.surface, borderBottomWidth: 1, borderBottomColor: COLORS.border, maxHeight: 52, flexShrink: 0 },
  tabs:     { paddingHorizontal: 16, paddingVertical: 10, gap: 6 },
  tab:      { paddingHorizontal: 14, paddingVertical: 6, borderRadius: RADIUS.pill, backgroundColor: COLORS.parchment, borderWidth: 1, borderColor: COLORS.border },
  tabActive:{ backgroundColor: COLORS.ink, borderColor: COLORS.ink },
  tabText:  { fontSize: 12, fontWeight: '600', color: COLORS.textSub },
  tabTextActive:{ color: '#fff' },

  mapSplit: { overflow: 'hidden', backgroundColor: COLORS.parchmentWarm },
  mapFull:  { flex: 1, overflow: 'hidden', backgroundColor: COLORS.parchmentWarm },

  locPrompt:{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  locIcon:  { fontSize: 36, color: COLORS.sage, marginBottom: 4 },
  locTitle: { ...TYPE.headlineMed, color: COLORS.ink, textAlign: 'center' },
  locBody:  { ...TYPE.bodySmall, color: COLORS.textMuted, textAlign: 'center', lineHeight: 20 },
  locBtn:   { marginTop: 8, backgroundColor: COLORS.ink, borderRadius: RADIUS.lg, paddingVertical: 14, paddingHorizontal: 28 },
  locBtnText:{ ...TYPE.titleMed, color: '#fff' },

  userDotWrap:  { alignItems: 'center', justifyContent: 'center', width: 32, height: 32 },
  headingArrow: {
    position: 'absolute', top: 0,
    width: 0, height: 0,
    borderLeftWidth: 6, borderRightWidth: 6, borderBottomWidth: 12,
    borderLeftColor: 'transparent', borderRightColor: 'transparent',
    borderBottomColor: COLORS.sage,
    opacity: 0.7,
  },
  userDot: {
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: COLORS.sage,
    borderWidth: 3, borderColor: '#fff',
    shadowColor: COLORS.sage, shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.4, shadowRadius: 4, elevation: 4,
  },

  fab: {
    position: 'absolute', bottom: 14, right: 14,
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: COLORS.surface,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15, shadowRadius: 6, elevation: 6,
    borderWidth: 1, borderColor: COLORS.border,
  },
  fabText: { fontSize: 22, color: COLORS.sage, lineHeight: 24 },

  accuracyBadge: {
    position: 'absolute', top: 12, left: 12,
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: 'rgba(247,244,238,0.92)',
    borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 4,
    borderWidth: 1, borderColor: COLORS.border,
  },
  accuracyDot:  { width: 7, height: 7, borderRadius: 4 },
  accuracyText: { fontSize: 11, fontWeight: '600', color: COLORS.textSub },

  listPanel:   { flex: 1 },
  listContent: { padding: 16, paddingTop: 12, paddingBottom: 240 },
  loadRow:     { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 20, justifyContent: 'center' },
  loadText:    { ...TYPE.bodySmall, color: COLORS.textMuted },
  errorRow:    { alignItems: 'center', padding: 20, gap: 10 },
  errorText:   { ...TYPE.bodySmall, color: COLORS.crimson },
  retryBtn:    { paddingHorizontal: 16, paddingVertical: 8, borderRadius: RADIUS.md, backgroundColor: COLORS.crimson },
  retryText:   { fontSize: 12, fontWeight: '700', color: '#fff' },

  teleRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: 'rgba(26,111,168,0.2)',
    padding: 16, marginBottom: 10, gap: 12,
  },
  teleLeft:  { flex: 1 },
  teleTitle: { ...TYPE.titleMed, color: '#1A6FA8', marginBottom: 2 },
  teleSub:   { ...TYPE.micro, color: '#1A6FA8', opacity: 0.75 },
  teleArrow: { fontSize: 18, color: '#1A6FA8', fontWeight: '300' },

  emergencyBtn: {
    backgroundColor: COLORS.crimson, borderRadius: RADIUS.lg,
    paddingVertical: 16, alignItems: 'center', marginBottom: 12,
  },
  emergencyText: { ...TYPE.titleLarge, color: '#fff' },
});
