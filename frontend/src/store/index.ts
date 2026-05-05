/**
 * Vaidya — Zustand global store
 * Slices: app (language/network), session (current triage), patient (profile), auth
 */

import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '@/constants';
import { saveLanguage } from '@/i18n';
import type { FullTriageResponse, Language, OfflinePrediction, TriageSession } from '@/types';
import type { AuthUser } from '@/services/auth';
import { authSignOut } from '@/services/auth';
import { setAuthToken } from '@/services/api';

// ── App slice ──────────────────────────────────────────────────────────────────
interface AppState {
  language:    Language;
  isOnline:    boolean;
  isReady:     boolean;
  setLanguage: (lang: Language) => Promise<void>;
  setOnline:   (online: boolean) => void;
  setReady:    (ready: boolean) => void;
}

// ── Session slice ──────────────────────────────────────────────────────────────
interface SessionState {
  currentSession:  FullTriageResponse | OfflinePrediction | null;
  sessionHistory:  TriageSession[];
  isAnalysing:     boolean;
  analysisStep:    number;
  symptomText:     string;
  severity:        number;
  duration:        string;
  audioUri:        string | null;
  imageUri:        string | null;
  imageTask:       'chest' | 'skin' | 'wound' | null;

  setCurrentSession:  (s: FullTriageResponse | OfflinePrediction | null) => void;
  setIsAnalysing:     (v: boolean) => void;
  setAnalysisStep:    (n: number) => void;
  setSymptomText:     (t: string) => void;
  setSeverity:        (n: number) => void;
  setDuration:        (d: string) => void;
  setAudioUri:        (uri: string | null) => void;
  setImageUri:        (uri: string | null) => void;
  setImageTask:       (task: 'chest' | 'skin' | 'wound' | null) => void;
  addToHistory:       (s: TriageSession) => Promise<void>;
  loadHistory:        () => Promise<void>;
  clearHistory:       () => Promise<void>;
  resetInput:         () => void;
}

// ── Patient slice ──────────────────────────────────────────────────────────────
interface PatientState {
  patientId:    string | null;
  ageGroup:     'child' | 'adult' | 'senior' | null;
  ashaName:     string | null;
  ashaPhone:    string | null;
  setPatientId: (id: string) => void;
  setAsha:      (name: string, phone: string) => Promise<void>;
  loadPatient:  () => Promise<void>;
}

// ── Auth slice ─────────────────────────────────────────────────────────────────
export interface PendingRegistration {
  name:     string;
  phone:    string;
  password: string;
  type:     'register' | 'reset';
  /** The OTP the user successfully verified — stored so reset-password can forward it to the backend */
  otp?:     string;
  /** OTP returned by backend when SMS delivery is unavailable (null when real SMS was sent) */
  demo_otp?: string | null;
}

interface AuthState {
  user:            AuthUser | null;
  token:           string | null;
  isAuthenticated: boolean;
  /** Temporary storage while OTP verification is in progress */
  pendingReg:      PendingRegistration | null;

  setAuth:         (user: AuthUser, token: string) => Promise<void>;
  setPendingReg:   (data: PendingRegistration | null) => void;
  logout:          () => Promise<void>;
  loadAuth:        () => Promise<void>;
}

// ── Combined store ────────────────────────────────────────────────────────────
export const useAppStore = create<AppState & SessionState & PatientState & AuthState>(
  (set, get) => ({

  // ── App ────────────────────────────────────────────────────────────────────
  language:  'en',
  isOnline:  true,
  isReady:   false,

  setLanguage: async (lang) => {
    await saveLanguage(lang);
    set({ language: lang });
  },

  setOnline: (online) => set({ isOnline: online }),
  setReady:  (ready)  => set({ isReady: ready }),

  // ── Session ────────────────────────────────────────────────────────────────
  currentSession: null,
  sessionHistory: [],
  isAnalysing:    false,
  analysisStep:   0,
  symptomText:    '',
  severity:       5,
  duration:       '',
  audioUri:       null,
  imageUri:       null,
  imageTask:      null,

  setCurrentSession: (s)    => set({ currentSession: s }),
  setIsAnalysing:    (v)    => set({ isAnalysing: v }),
  setAnalysisStep:   (n)    => set({ analysisStep: n }),
  setSymptomText:    (t)    => set({ symptomText: t }),
  setSeverity:       (n)    => set({ severity: n }),
  setDuration:       (d)    => set({ duration: d }),
  setAudioUri:       (uri)  => set({ audioUri: uri }),
  setImageUri:       (uri)  => set({ imageUri: uri }),
  setImageTask:      (task) => set({ imageTask: task }),

  resetInput: () => set({
    symptomText: '',
    severity:    5,
    duration:    '',
    audioUri:    null,
    imageUri:    null,
    imageTask:   null,
    analysisStep: 0,
  }),

  addToHistory: async (session) => {
    const existing = get().sessionHistory;
    const updated  = [session, ...existing].slice(0, 20);
    set({ sessionHistory: updated });
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.SESSIONS, JSON.stringify(updated));
    } catch {}
    // Mirror to Firestore when signed in — imported lazily to avoid a
    // module-level crash before React mounts
    const uid = get().user?.id;
    if (uid && !uid.startsWith('demo-')) {
      try {
        const { saveSessionToFirestore, incrementSessionCounter } =
          require('@/services/firestore') as typeof import('@/services/firestore');
        saveSessionToFirestore(uid, session);
        incrementSessionCounter();
      } catch {}
    }
  },

  loadHistory: async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEYS.SESSIONS);
      if (raw) set({ sessionHistory: JSON.parse(raw) });
    } catch {}
  },

  clearHistory: async () => {
    await AsyncStorage.removeItem(STORAGE_KEYS.SESSIONS);
    set({ sessionHistory: [] });
  },

  // ── Patient ────────────────────────────────────────────────────────────────
  patientId: null,
  ageGroup:  null,
  ashaName:  null,
  ashaPhone: null,

  setPatientId: (id) => set({ patientId: id }),

  setAsha: async (name, phone) => {
    set({ ashaName: name, ashaPhone: phone });
    try {
      await AsyncStorage.setItem(
        STORAGE_KEYS.ASHA_CONTACT,
        JSON.stringify({ name, phone }),
      );
    } catch {}
  },

  loadPatient: async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEYS.ASHA_CONTACT);
      if (raw) {
        const { name, phone } = JSON.parse(raw);
        set({ ashaName: name, ashaPhone: phone });
      }
    } catch {}
  },

  // ── Auth ───────────────────────────────────────────────────────────────────
  user:            null,
  token:           null,
  isAuthenticated: false,
  pendingReg:      null,

  setAuth: async (user, token) => {
    setAuthToken(token);
    set({ user, token, isAuthenticated: true });
    try {
      await AsyncStorage.multiSet([
        [STORAGE_KEYS.AUTH_TOKEN, token],
        [STORAGE_KEYS.AUTH_USER,  JSON.stringify(user)],
      ]);
    } catch {}
  },

  setPendingReg: (data) => set({ pendingReg: data }),

  logout: async () => {
    await authSignOut();
    setAuthToken(null);
    set({
      user:            null,
      token:           null,
      isAuthenticated: false,
      pendingReg:      null,
      currentSession:  null,
      sessionHistory:  [],
    });
    try {
      await AsyncStorage.multiRemove([
        STORAGE_KEYS.AUTH_TOKEN,
        STORAGE_KEYS.AUTH_USER,
        STORAGE_KEYS.SESSIONS,
      ]);
    } catch {}
  },

  loadAuth: async () => {
    try {
      const results = await AsyncStorage.multiGet([
        STORAGE_KEYS.AUTH_TOKEN,
        STORAGE_KEYS.AUTH_USER,
      ]);
      const token   = results[0]?.[1] ?? null;
      const userRaw = results[1]?.[1] ?? null;
      if (token && token !== 'demo-token' && userRaw) {
        try {
          const user: AuthUser = JSON.parse(userRaw);
          setAuthToken(token);
          set({ user, token, isAuthenticated: true });
        } catch {
          // Corrupt stored user — clear it so the app doesn't get stuck
          await AsyncStorage.multiRemove([STORAGE_KEYS.AUTH_TOKEN, STORAGE_KEYS.AUTH_USER]);
        }
      } else if (token === 'demo-token') {
        // Demo sessions must not auto-restore — force re-login on next app start
        await AsyncStorage.multiRemove([STORAGE_KEYS.AUTH_TOKEN, STORAGE_KEYS.AUTH_USER]);
      }
    } catch {}
  },
}));
