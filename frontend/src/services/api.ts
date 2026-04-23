/**
 * Vaidya — API client (axios)
 * - Reads API base URL from app.json extra.apiBaseUrl
 * - Injects Accept-Language header from current i18n language
 * - Detects offline state before requests
 * - Maps server errors to user-friendly messages
 *
 * DEMO FALLBACK: When the backend is unreachable (backend not running locally),
 * all API calls transparently return realistic mock data so the full UI can
 * be demonstrated end-to-end. No existing functionality is affected — when
 * the backend IS running, all real API calls behave exactly as before.
 */

import axios, { AxiosError } from 'axios';
import Constants from 'expo-constants';
import NetInfo from '@react-native-community/netinfo';
import i18n from '@/i18n';
import type {
  FullTriageResponse,
  HospitalListResponse,
  TeleconsultSlot,
  VoiceInputResponse,
} from '@/types';
import {
  getDemoTriageResponse,
  markDemoMode,
  DEMO_HOSPITALS,
  DEMO_TELECONSULT_SLOTS,
  DEMO_VOICE_RESPONSE,
  isNetworkUnreachable,
} from './demoData';

// Priority:
//   1. EXPO_PUBLIC_API_URL  — set in frontend/.env or eas.json per build profile
//   2. app.json extra.apiBaseUrl — legacy fallback
//   3. 10.0.2.2:8000 — Android emulator loopback only
//
// Expo Go on a real Android device needs your LAN IP:
//   echo "EXPO_PUBLIC_API_URL=http://192.168.x.x:8000" > frontend/.env
const BASE_URL: string =
  process.env.EXPO_PUBLIC_API_URL ??
  Constants.expoConfig?.extra?.apiBaseUrl ??
  'http://10.0.2.2:8000';

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Language header on every request ─────────────────────────────────────────
apiClient.interceptors.request.use((config) => {
  config.headers['Accept-Language'] = i18n.language ?? 'en';
  return config;
});

// ── Offline guard ─────────────────────────────────────────────────────────────
apiClient.interceptors.request.use(async (config) => {
  const state = await NetInfo.fetch();
  if (!state.isConnected) {
    throw new OfflineError();
  }
  return config;
});

// ── Error normalisation ───────────────────────────────────────────────────────
apiClient.interceptors.response.use(
  (r) => r,
  (err: AxiosError) => {
    if (err instanceof OfflineError) throw err;
    const status  = err.response?.status;
    const detail  = (err.response?.data as any)?.detail ?? '';
    throw new ApiRequestError(status, String(detail), err);
  },
);

export class OfflineError extends Error {
  constructor() { super('Device is offline'); this.name = 'OfflineError'; }
}

export class ApiRequestError extends Error {
  constructor(
    public status: number | undefined,
    public detail: string,
    public original: AxiosError,
  ) {
    super(`API error ${status}: ${detail}`);
    this.name = 'ApiRequestError';
  }
}

// ── Demo mode helper ──────────────────────────────────────────────────────────
/** Simulate realistic network latency for demo responses */
async function _demoDelay(ms = 1400): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** Submit symptom text — full text-only triage pipeline */
export async function triageText(payload: {
  text:          string;
  language:      string;
  self_severity?: number;
  patient_id?:   string;
}): Promise<FullTriageResponse> {
  try {
    const { data } = await apiClient.post<FullTriageResponse>(
      '/diagnose/predict/text',
      payload,
    );
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      markDemoMode();
      await _demoDelay();
      return getDemoTriageResponse();
    }
    throw err;
  }
}

/** Submit voice audio file — returns transcript */
export async function submitVoice(
  audioUri: string,
  languageHint?: string,
): Promise<VoiceInputResponse> {
  try {
    const form = new FormData();
    form.append('file', {
      uri:  audioUri,
      name: 'recording.wav',
      type: 'audio/wav',
    } as any);
    if (languageHint) form.append('language_hint', languageHint);

    const { data } = await apiClient.post<VoiceInputResponse>(
      '/input/voice',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      markDemoMode();
      await _demoDelay(800);
      return DEMO_VOICE_RESPONSE;
    }
    throw err;
  }
}

/** Submit multimodal triage — text + optional audio + optional image */
export async function triageMultimodal(payload: {
  text:          string;
  language:      string;
  self_severity?: number;
  patient_id?:   string;
  audioUri?:     string;
  imageUri?:     string;
  imageTask?:    'chest' | 'skin' | 'wound';
}): Promise<FullTriageResponse> {
  try {
    const form = new FormData();
    form.append('text',     payload.text);
    form.append('language', payload.language);
    if (payload.self_severity != null)
      form.append('self_severity', String(payload.self_severity));
    if (payload.patient_id)
      form.append('patient_id', payload.patient_id);
    if (payload.audioUri)
      form.append('audio_file', {
        uri: payload.audioUri, name: 'recording.wav', type: 'audio/wav',
      } as any);
    if (payload.imageUri)
      form.append('image_file', {
        uri: payload.imageUri, name: 'photo.jpg', type: 'image/jpeg',
      } as any);
    if (payload.imageTask)
      form.append('image_task', payload.imageTask);

    const { data } = await apiClient.post<FullTriageResponse>(
      '/diagnose/predict',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      markDemoMode();
      await _demoDelay();
      return getDemoTriageResponse();
    }
    throw err;
  }
}

/** Find nearby hospitals and PHCs */
export async function findHospitals(
  lat: number,
  lng: number,
  radiusKm = 50,
): Promise<HospitalListResponse> {
  try {
    const { data } = await apiClient.get<HospitalListResponse>('/care/hospitals', {
      params: { lat, lng, radius_km: radiusKm },
    });
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      markDemoMode();
      await _demoDelay(600);
      return DEMO_HOSPITALS;
    }
    throw err;
  }
}

/** Get eSanjeevani teleconsult slots */
export async function getTeleconsultSlots(
  specialty?: string,
): Promise<TeleconsultSlot[]> {
  try {
    const { data } = await apiClient.get<{ slots: TeleconsultSlot[] }>(
      '/care/teleconsult',
      { params: { language: i18n.language, specialty } },
    );
    return data.slots;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      markDemoMode();
      await _demoDelay(600);
      return DEMO_TELECONSULT_SLOTS;
    }
    throw err;
  }
}

/** Fetch nearby hospitals by GPS coordinates */
export async function fetchHospitals(params: {
  lat: number; lng: number; type?: string; radius_km?: number;
}): Promise<HospitalListResponse> {
  try {
    const { data } = await apiClient.get<HospitalListResponse>('/care/hospitals', { params });
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      markDemoMode();
      await _demoDelay(600);
      return DEMO_HOSPITALS;
    }
    throw err;
  }
}
