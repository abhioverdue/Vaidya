import type { Language, TriageLevel } from '@/types';

// ── Design System — Vaidya Redesign ──────────────────────────────────────────
// Direction: Deep ink + warm parchment + surgical crimson
// "Refined clinical" — the kind of care that feels considered

export const COLORS = {
  // Ink — primary surfaces
  ink:           '#0F1117',
  inkDeep:       '#080A0F',
  inkMid:        '#1C2030',
  inkSoft:       '#2A2F42',
  inkGhost:      'rgba(15,17,23,0.06)',

  // Parchment — warm off-white backgrounds
  parchment:     '#F7F4EE',
  parchmentWarm: '#EEE9DF',
  parchmentCool: '#F0EFF5',
  surface:       '#FFFFFF',
  surfaceWarm:   '#FDFCF9',

  // Crimson — accent, urgency, action
  crimson:       '#C23B22',
  crimsonLight:  '#E05038',
  crimsonDeep:   '#8B2A18',
  crimsonGhost:  'rgba(194,59,34,0.08)',

  // Sage — secondary accent, success states
  sage:          '#3A5F52',
  sageLight:     '#4E7A6A',
  sageDark:      '#243D34',
  sageGhost:     'rgba(58,95,82,0.08)',

  // Gold — warning, elevated triage
  gold:          '#9A6B1F',
  goldLight:     '#C28A2E',
  goldGhost:     'rgba(154,107,31,0.10)',

  // Text hierarchy
  text:          '#0F1117',
  textSub:       '#3D4258',
  textMuted:     '#7A7F96',
  textFaint:     '#AEAFC0',
  textInverse:   '#F7F4EE',

  // Borders
  border:        'rgba(15,17,23,0.10)',
  borderMid:     'rgba(15,17,23,0.18)',
  borderStrong:  'rgba(15,17,23,0.28)',

  // Triage — deliberately muted, not garish
  t1:  '#2E6B4A',
  t2:  '#4A7A35',
  t3:  '#8A6820',
  t4:  '#B04A20',
  t5:  '#8B1C1C',

  // Aliases for backward compat
  primary:       '#3A5F52',
  primaryLight:  '#4E7A6A',
  primaryDark:   '#243D34',
  primaryGhost:  'rgba(58,95,82,0.08)',
  primaryGlow:   'rgba(58,95,82,0.14)',
  accent:        '#C23B22',
  background:    '#F7F4EE',
  canvas:        '#EEE9DF',
  error:         '#8B1C1C',
  errorLight:    '#FDF0EE',
  warning:       '#9A6B1F',
  warningLight:  '#FEF8EC',
  success:       '#2E6B4A',
  successLight:  '#EAF4EE',
  info:          '#1A4A7A',
  infoLight:     '#EAF0FA',
  shadow:        'rgba(15,17,23,0.06)',
  shadowMedium:  'rgba(15,17,23,0.12)',
  textSecondary: '#3D4258',
  textDisabled:  '#AEAFC0',
} as const;

// ── Typography ────────────────────────────────────────────────────────────────
// Using system fonts that approximate DM Serif / DM Sans on device
export const TYPE = {
  // Display — large headlines
  display:      { fontSize: 36, fontWeight: '700' as const, letterSpacing: -1.2, lineHeight: 42 },
  displayMed:   { fontSize: 28, fontWeight: '700' as const, letterSpacing: -0.8, lineHeight: 34 },

  // Headline
  headlineLarge:{ fontSize: 22, fontWeight: '700' as const, letterSpacing: -0.4, lineHeight: 28 },
  headlineMed:  { fontSize: 18, fontWeight: '700' as const, letterSpacing: -0.2, lineHeight: 24 },

  // Title
  titleLarge:   { fontSize: 16, fontWeight: '600' as const, letterSpacing: -0.1, lineHeight: 22 },
  titleMed:     { fontSize: 14, fontWeight: '600' as const, lineHeight: 20 },

  // Body
  bodyLarge:    { fontSize: 16, fontWeight: '400' as const, lineHeight: 26 },
  bodyMed:      { fontSize: 14, fontWeight: '400' as const, lineHeight: 22 },
  bodySmall:    { fontSize: 13, fontWeight: '400' as const, lineHeight: 20 },

  // Label & micro
  label:        { fontSize: 11, fontWeight: '600' as const, letterSpacing: 1.2, lineHeight: 16 },
  micro:        { fontSize: 10, fontWeight: '500' as const, letterSpacing: 0.5, lineHeight: 14 },
} as const;

export const SPACE = {
  xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32, huge: 48,
} as const;

export const RADIUS = {
  xs: 3, sm: 6, md: 10, lg: 14, xl: 18, xxl: 24, pill: 100, circle: 999,
} as const;

export const TRIAGE_CONFIG: Record<TriageLevel, {
  color: string; bgColor: string; borderColor: string; icon: string; label: string;
}> = {
  1: { color: COLORS.t1, bgColor: '#EDF6F1', borderColor: '#B8D9C8', icon: '', label: 'Self Care' },
  2: { color: COLORS.t2, bgColor: '#EEF5E8', borderColor: '#BDDBA8', icon: '', label: 'Watch & Wait' },
  3: { color: COLORS.t3, bgColor: '#FEF8EC', borderColor: '#E8D098', icon: '', label: 'See a Doctor' },
  4: { color: COLORS.t4, bgColor: '#FEF2EE', borderColor: '#E8B098', icon: '', label: 'Urgent Care' },
  5: { color: COLORS.t5, bgColor: '#FCEAEA', borderColor: '#E8A0A0', icon: '', label: 'Emergency' },
};

export const LANGUAGES: Array<{ code: Language; name: string; nativeName: string; rtl: boolean; flag: string }> = [
  { code: 'en', name: 'English',  nativeName: 'English',  rtl: false, flag: '' },
  { code: 'hi', name: 'Hindi',    nativeName: 'हिन्दी',   rtl: false, flag: '' },
  { code: 'ta', name: 'Tamil',    nativeName: 'தமிழ்',    rtl: false, flag: '' },
];

export const QUICK_SYMPTOMS: Record<Language, string[]> = {
  en: ['Fever', 'Cough', 'Headache', 'Vomiting', 'Diarrhoea', 'Chest pain', 'Breathlessness', 'Body ache', 'Rash', 'Fatigue'],
  hi: ['बुखार', 'खांसी', 'सिरदर्द', 'उल्टी', 'दस्त', 'सीने में दर्द', 'सांस की तकलीफ', 'बदन दर्द', 'चकत्ते', 'थकान'],
  ta: ['காய்ச்சல்', 'இருமல்', 'தலைவலி', 'வாந்தி', 'வயிற்றுப்போக்கு', 'மார்பு வலி', 'மூச்சு திணறல்', 'உடல் வலி', 'தடிப்பு', 'சோர்வு'],
};

export const API_TIMEOUT_MS          = 30_000;
export const TFLITE_MODEL_FILENAME   = 'vaidya_symptom_classifier.tflite';
export const TFLITE_LABELS_FILENAME  = 'disease_labels.json';
export const MIN_SYMPTOMS_FOR_TFLITE = 3;

export const STORAGE_KEYS = {
  LANGUAGE:        'vaidya:language',
  SESSIONS:        'vaidya:sessions',
  PATIENT_PROFILE: 'vaidya:patient',
  ASHA_CONTACT:    'vaidya:asha',
  LAST_SESSION:    'vaidya:last_session',
  CAUTION_SEEN:    'vaidya:caution_seen',
  CONSENT_GIVEN:   'vaidya:consent_given',
  // Auth
  AUTH_TOKEN:      'vaidya:auth_token',
  AUTH_USER:       'vaidya:auth_user',
  PENDING_REG:     'vaidya:pending_reg',
} as const;
