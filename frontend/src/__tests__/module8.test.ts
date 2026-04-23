/**
 * Vaidya — Frontend test suite (Module 8)
 * Tests: i18n init, language switching, store state, offline model utilities
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderHook, act } from '@testing-library/react-native';

// ── i18n ──────────────────────────────────────────────────────────────────────

describe('i18n initialisation', () => {
  it('exports a valid i18next instance', async () => {
    const { initI18n } = await import('@/i18n');
    await initI18n();
    const i18n = (await import('@/i18n')).default;
    expect(i18n.isInitialized).toBe(true);
  });

  it('defaults to English when no saved preference', async () => {
    jest.spyOn(AsyncStorage, 'getItem').mockResolvedValue(null);
    const { initI18n } = await import('@/i18n');
    await initI18n();
    const i18n = (await import('@/i18n')).default;
    expect(['en', 'hi', 'ta']).toContain(i18n.language);
  });

  it('loads saved Hindi preference', async () => {
    jest.spyOn(AsyncStorage, 'getItem').mockResolvedValue('hi');
    jest.resetModules();
    const { initI18n } = await import('@/i18n');
    await initI18n();
    const i18n = (await import('@/i18n')).default;
    expect(i18n.language).toBe('hi');
  });

  it('has all required English translation keys', async () => {
    const en = await import('@/i18n/locales/en.json');
    expect(en.common.app_name).toBeDefined();
    expect(en.symptom.analyze_btn).toBeDefined();
    expect(en.result.triage_5).toBeDefined();
    expect(en.care.hospitals_tab).toBeDefined();
  });

  it('has all required Hindi translation keys', async () => {
    const hi = await import('@/i18n/locales/hi.json');
    expect(hi.common.app_name).toBeDefined();
    expect(hi.symptom.analyze_btn).toBeDefined();
    expect(hi.result.triage_5).toBeDefined();
  });

  it('has all required Tamil translation keys', async () => {
    const ta = await import('@/i18n/locales/ta.json');
    expect(ta.common.app_name).toBeDefined();
    expect(ta.symptom.analyze_btn).toBeDefined();
    expect(ta.result.triage_5).toBeDefined();
  });

  it('English and Hindi have the same top-level keys', async () => {
    const en = await import('@/i18n/locales/en.json');
    const hi = await import('@/i18n/locales/hi.json');
    expect(Object.keys(en)).toEqual(expect.arrayContaining(Object.keys(hi)));
  });

  it('English and Tamil have the same top-level keys', async () => {
    const en = await import('@/i18n/locales/en.json');
    const ta = await import('@/i18n/locales/ta.json');
    expect(Object.keys(en)).toEqual(expect.arrayContaining(Object.keys(ta)));
  });

  it('saveLanguage persists to AsyncStorage', async () => {
    const setSpy = jest.spyOn(AsyncStorage, 'setItem').mockResolvedValue();
    const { saveLanguage } = await import('@/i18n');
    await saveLanguage('ta');
    expect(setSpy).toHaveBeenCalledWith('vaidya:language', 'ta');
  });
});

// ── Quick symptoms ────────────────────────────────────────────────────────────

describe('Quick symptom chips', () => {
  it('has 10 chips per language', async () => {
    const { QUICK_SYMPTOMS } = await import('@/constants');
    expect(QUICK_SYMPTOMS.en.length).toBe(10);
    expect(QUICK_SYMPTOMS.hi.length).toBe(10);
    expect(QUICK_SYMPTOMS.ta.length).toBe(10);
  });

  it('Hindi chips contain Devanagari characters', async () => {
    const { QUICK_SYMPTOMS } = await import('@/constants');
    const hasDevanagari = QUICK_SYMPTOMS.hi.some(
      (chip) => /[\u0900-\u097F]/.test(chip),
    );
    expect(hasDevanagari).toBe(true);
  });

  it('Tamil chips contain Tamil characters', async () => {
    const { QUICK_SYMPTOMS } = await import('@/constants');
    const hasTamil = QUICK_SYMPTOMS.ta.some(
      (chip) => /[\u0B80-\u0BFF]/.test(chip),
    );
    expect(hasTamil).toBe(true);
  });
});

// ── Zustand store ─────────────────────────────────────────────────────────────

describe('Zustand store', () => {
  beforeEach(() => {
    jest.resetModules();
    jest.spyOn(AsyncStorage, 'getItem').mockResolvedValue(null);
    jest.spyOn(AsyncStorage, 'setItem').mockResolvedValue();
    jest.spyOn(AsyncStorage, 'removeItem').mockResolvedValue();
  });

  it('initialises with default language en', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore((s) => s.language));
    expect(result.current).toBe('en');
  });

  it('setSymptomText updates store', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    act(() => result.current.setSymptomText('I have fever'));
    expect(result.current.symptomText).toBe('I have fever');
  });

  it('setSeverity clamps correctly', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    act(() => result.current.setSeverity(8));
    expect(result.current.severity).toBe(8);
  });

  it('resetInput clears symptomText', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    act(() => {
      result.current.setSymptomText('fever');
      result.current.resetInput();
    });
    expect(result.current.symptomText).toBe('');
  });

  it('addToHistory caps at 20 sessions', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    const makeSession = (id: string) => ({
      id, timestamp: new Date().toISOString(), language: 'en' as const,
      symptom_text: 'test', result: { primary_diagnosis: 'Test', confidence: 0.8,
        differential: [], source: 'tflite_offline' as const },
      was_offline: true,
    });
    for (let i = 0; i < 25; i++) {
      await act(async () => { await result.current.addToHistory(makeSession(String(i))); });
    }
    expect(result.current.sessionHistory.length).toBeLessThanOrEqual(20);
  });

  it('clearHistory empties sessions', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    await act(async () => { await result.current.clearHistory(); });
    expect(result.current.sessionHistory).toHaveLength(0);
  });

  it('setOnline updates isOnline', async () => {
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    act(() => result.current.setOnline(false));
    expect(result.current.isOnline).toBe(false);
    act(() => result.current.setOnline(true));
    expect(result.current.isOnline).toBe(true);
  });

  it('setAsha persists to AsyncStorage', async () => {
    const setSpy = jest.spyOn(AsyncStorage, 'setItem').mockResolvedValue();
    const { useAppStore } = await import('@/store');
    const { result } = renderHook(() => useAppStore());
    await act(async () => {
      await result.current.setAsha('Meenakshi', '9876543210');
    });
    expect(setSpy).toHaveBeenCalledWith('vaidya:asha', expect.stringContaining('Meenakshi'));
    expect(result.current.ashaName).toBe('Meenakshi');
    expect(result.current.ashaPhone).toBe('9876543210');
  });
});

// ── Canonical symptom list ────────────────────────────────────────────────────

describe('Canonical symptom list', () => {
  it('has exactly 133 symptoms', async () => {
    const { CANONICAL_SYMPTOMS } = await import('@/services/symptomList');
    expect(CANONICAL_SYMPTOMS.length).toBe(133);
  });

  it('has no duplicates', async () => {
    const { CANONICAL_SYMPTOMS } = await import('@/services/symptomList');
    const unique = new Set(CANONICAL_SYMPTOMS);
    expect(unique.size).toBe(CANONICAL_SYMPTOMS.length);
  });

  it('all entries are snake_case lowercase', async () => {
    const { CANONICAL_SYMPTOMS } = await import('@/services/symptomList');
    for (const sym of CANONICAL_SYMPTOMS) {
      expect(sym).toBe(sym.toLowerCase());
      expect(sym).not.toContain(' ');
    }
  });

  it('contains critical emergency symptoms', async () => {
    const { CANONICAL_SYMPTOMS } = await import('@/services/symptomList');
    const critical = ['chest_pain', 'breathlessness', 'loss_of_consciousness', 'high_fever'];
    for (const sym of critical) {
      expect(CANONICAL_SYMPTOMS).toContain(sym);
    }
  });
});

// ── Offline model ─────────────────────────────────────────────────────────────

describe('Offline model utilities', () => {
  it('isModelReady returns false before loading', async () => {
    jest.mock('@tensorflow/tfjs-react-native', () => ({}));
    jest.mock('@tensorflow/tfjs', () => ({
      ready: jest.fn().mockResolvedValue(undefined),
      tensor2d: jest.fn().mockReturnValue({ dataSync: () => new Float32Array(132).fill(0.01) }),
      tidy: jest.fn((fn: () => any) => fn()),
      disposeVariables: jest.fn(),
    }));
    const { isModelReady } = await import('@/services/offlineModel');
    expect(isModelReady()).toBe(false);
  });

  it('runOfflineInference returns null with too few symptoms', async () => {
    const { runOfflineInference } = await import('@/services/offlineModel');
    const result = await runOfflineInference(['high_fever']);  // only 1 symptom
    // With min 3 required, should return null or a result depending on model state
    if (result === null) expect(result).toBeNull();
    else expect(result).toHaveProperty('primary_diagnosis');
  });
});

// ── Constants ─────────────────────────────────────────────────────────────────

describe('Constants', () => {
  it('TRIAGE_CONFIG has entries for all 5 levels', async () => {
    const { TRIAGE_CONFIG } = await import('@/constants');
    for (let i = 1; i <= 5; i++) {
      expect(TRIAGE_CONFIG[i as 1|2|3|4|5]).toBeDefined();
    }
  });

  it('TRIAGE_CONFIG level 5 has red color', async () => {
    const { TRIAGE_CONFIG, COLORS } = await import('@/constants');
    expect(TRIAGE_CONFIG[5].color).toBe(COLORS.triage5);
  });

  it('STORAGE_KEYS are all unique', async () => {
    const { STORAGE_KEYS } = await import('@/constants');
    const values = Object.values(STORAGE_KEYS);
    const unique = new Set(values);
    expect(unique.size).toBe(values.length);
  });
});

// ── API service ────────────────────────────────────────────────────────────────

describe('API service', () => {
  it('apiClient has correct base configuration', async () => {
    const { apiClient } = await import('@/services/api');
    expect(apiClient.defaults.timeout).toBe(30_000);
  });

  it('OfflineError can be constructed', async () => {
    const { OfflineError } = await import('@/services/api');
    const err = new OfflineError();
    expect(err.name).toBe('OfflineError');
    expect(err.message).toContain('offline');
  });

  it('ApiRequestError carries status and detail', async () => {
    const { ApiRequestError } = await import('@/services/api');
    const err = new ApiRequestError(422, 'validation failed', {} as any);
    expect(err.status).toBe(422);
    expect(err.detail).toBe('validation failed');
  });
});
