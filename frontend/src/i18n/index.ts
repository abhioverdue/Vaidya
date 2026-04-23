/**
 * Vaidya — i18next configuration
 *
 * Language detection priority:
 *   1. AsyncStorage (user's saved preference from settings)
 *   2. Device locale (RN's I18nManager gives device language)
 *   3. 'en' fallback
 *
 * Supported: en | hi | ta
 * All translations are bundled — no network required in offline mode.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NativeModules, Platform } from 'react-native';

import en from './locales/en.json';
import hi from './locales/hi.json';
import ta from './locales/ta.json';

import { STORAGE_KEYS } from '@/constants';
import type { Language } from '@/types';

const SUPPORTED: Language[] = ['en', 'hi', 'ta'];

// ── Detect device language ────────────────────────────────────────────────────
function getDeviceLanguage(): Language {
  const raw: string =
    Platform.OS === 'android'
      ? NativeModules.I18nManager?.localeIdentifier ?? 'en'
      : NativeModules.SettingsManager?.settings?.AppleLocale ??
        NativeModules.SettingsManager?.settings?.AppleLanguages?.[0] ??
        'en';

  const code = raw.split(/[-_]/)[0].toLowerCase() as Language;
  return SUPPORTED.includes(code) ? code : 'en';
}

// ── Load saved preference from AsyncStorage ───────────────────────────────────
async function getSavedLanguage(): Promise<Language | null> {
  try {
    const saved = await AsyncStorage.getItem(STORAGE_KEYS.LANGUAGE);
    if (saved && SUPPORTED.includes(saved as Language)) {
      return saved as Language;
    }
  } catch {}
  return null;
}

// ── Persist language selection ────────────────────────────────────────────────
export async function saveLanguage(lang: Language): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEYS.LANGUAGE, lang);
  await i18n.changeLanguage(lang);
}

// ── Initialise i18next ────────────────────────────────────────────────────────
export async function initI18n(): Promise<void> {
  const saved   = await getSavedLanguage();
  const device  = getDeviceLanguage();
  const initial = saved ?? device;

  await i18n
    .use(initReactI18next)
    .init({
      resources: {
        en: { translation: en },
        hi: { translation: hi },
        ta: { translation: ta },
      },
      lng:            initial,
      fallbackLng:    'en',
      defaultNS:      'translation',
      interpolation:  { escapeValue: false },
      compatibilityJSON: 'v4',    // required for React Native
    });
}

export default i18n;
