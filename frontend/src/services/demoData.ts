/**
 * Vaidya — Demo / fallback data
 *
 * When the backend is unreachable (no local server running), the API layer
 * returns these realistic mock responses so the full UI flow can be
 * demonstrated end-to-end without a running backend.
 *
 * All existing logic is preserved — this file is ONLY used when an API call
 * fails with a network-unreachable error (ECONNREFUSED / network request failed).
 * When the real backend IS running, every API call behaves exactly as before.
 */

import type {
  FullTriageResponse,
  HospitalListResponse,
  TeleconsultSlot,
  VoiceInputResponse,
} from '@/types';

// ── Triage / diagnosis ─────────────────────────────────────────────────────────

const DEMO_TRIAGE_RESPONSES: FullTriageResponse[] = [
  {
    session_id: 'demo-001',
    input_language: 'en',
    created_at: new Date().toISOString(),
    extracted: {
      symptoms: ['fever', 'cough', 'sore_throat', 'runny_nose'],
      duration: '2 days',
      severity_estimate: 4,
      body_parts: ['throat', 'chest'],
      raw_keywords: ['fever', 'cough', 'sore throat', 'runny nose'],
    },
    diagnosis: {
      primary_diagnosis: 'Viral Upper Respiratory Infection',
      confidence: 0.82,
      differential: [
        { disease: 'Influenza', confidence: 0.11, confidence_label: 'Low' },
        { disease: 'Bacterial Pharyngitis', confidence: 0.07, confidence_label: 'Low' },
      ],
      diagnosis_source: 'fusion',
      red_flags: [],
      precautions: [
        'Rest and stay hydrated',
        'Avoid cold beverages',
        'Steam inhalation may help',
        'Use a soft cloth to blow your nose',
      ],
      description: 'A common viral infection of the upper airways including the nose, throat, and sinuses.',
      disclaimer: 'This is an AI-assisted assessment. Always consult a licensed doctor for a confirmed diagnosis.',
    },
    triage: {
      level: 2,
      label: 'Watch & Wait',
      reasoning: 'Symptoms are consistent with a mild viral infection. No red flags detected. Monitor for worsening fever or breathing difficulty.',
      asha_assigned: {
        name: 'Meena Devi',
        phone: '9876543210',
        village: 'Maduranthakam',
        distance_km: 1.2,
      },
      follow_up_at: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
    },
    audio_result: {
      label: 'cough_healthy',
      confidence: 0.65,
      confidence_label: 'Medium',
      predictions: [
        { label: 'cough_healthy', confidence: 0.65 },
        { label: 'cough_severe', confidence: 0.25 },
        { label: 'other', confidence: 0.10 },
      ],
    },
    vision_result: {
      top_prediction: 'normal_chest_xray',
      dataset_type: 'chest',
      all_predictions: [
        { label: 'normal_chest_xray', confidence: 0.78 },
        { label: 'pneumonia', confidence: 0.15 },
        { label: 'tuberculosis', confidence: 0.07 },
      ],
      signal_source: 'vision_model',
    },
    fusion_weights: {
      nlp: 0.5,
      audio: 0.25,
      vision: 0.25,
    },
  },
  {
    session_id: 'demo-002',
    input_language: 'en',
    created_at: new Date().toISOString(),
    extracted: {
      symptoms: ['vomiting', 'diarrhoea', 'abdominal_pain', 'nausea'],
      duration: '1 day',
      severity_estimate: 6,
      body_parts: ['abdomen'],
      raw_keywords: ['vomiting', 'loose stools', 'stomach pain', 'nausea'],
    },
    diagnosis: {
      primary_diagnosis: 'Acute Gastroenteritis',
      confidence: 0.76,
      differential: [
        { disease: 'Food Poisoning', confidence: 0.15, confidence_label: 'Low' },
        { disease: 'Irritable Bowel Syndrome', confidence: 0.09, confidence_label: 'Low' },
      ],
      diagnosis_source: 'xgboost',
      red_flags: ['Signs of dehydration', 'Blood in stool'],
      precautions: [
        'Drink ORS (oral rehydration solution) frequently',
        'Avoid solid food for a few hours',
        'Do not take anti-diarrhoeal drugs without doctor advice',
        'Watch for signs of dehydration: dry mouth, no urination',
      ],
      description: 'Inflammation of the stomach and intestines, typically caused by a viral or bacterial infection.',
      disclaimer: 'This is an AI-assisted assessment. Always consult a licensed doctor for a confirmed diagnosis.',
    },
    triage: {
      level: 3,
      label: 'See a Doctor',
      reasoning: 'Dehydration risk is present. Red flags noted. Recommend PHC visit within 24 hours.',
      asha_assigned: null,
      follow_up_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    },
  },
  {
    session_id: 'demo-003',
    input_language: 'en',
    created_at: new Date().toISOString(),
    extracted: {
      symptoms: ['headache', 'fatigue', 'neck_stiffness'],
      duration: 'a few hours',
      severity_estimate: 3,
      body_parts: ['head', 'neck'],
      raw_keywords: ['headache', 'tired', 'neck stiff'],
    },
    diagnosis: {
      primary_diagnosis: 'Tension Headache',
      confidence: 0.71,
      differential: [
        { disease: 'Migraine', confidence: 0.19, confidence_label: 'Low' },
        { disease: 'Sinusitis', confidence: 0.10, confidence_label: 'Low' },
      ],
      diagnosis_source: 'llm_gemini',
      red_flags: [],
      precautions: [
        'Rest in a quiet, dark room',
        'Stay well hydrated',
        'Apply a cold or warm compress to your forehead',
        'Avoid screens and bright light',
      ],
      description: 'A common type of headache often triggered by stress, poor posture, or dehydration.',
      icd_hint: 'G44.2',
      disclaimer: 'This is an AI-assisted assessment. Always consult a licensed doctor for a confirmed diagnosis.',
    },
    triage: {
      level: 1,
      label: 'Self Care',
      reasoning: 'No red flags. Symptoms are consistent with a tension headache. Self-care measures are appropriate.',
      asha_assigned: null,
      follow_up_at: null,
    },
  },
];

let _demoIndex = 0;

/** Returns a rotating demo triage response (varies on each call for variety). */
export function getDemoTriageResponse(): FullTriageResponse {
  const resp = DEMO_TRIAGE_RESPONSES[_demoIndex % DEMO_TRIAGE_RESPONSES.length];
  _demoIndex += 1;
  return { ...resp, session_id: `demo-${Date.now()}`, created_at: new Date().toISOString() };
}

// ── Hospitals ──────────────────────────────────────────────────────────────────

export const DEMO_HOSPITALS: HospitalListResponse = {
  results: [
    {
      id: 'demo-hosp-001',
      name: 'Primary Health Centre, Kanchipuram',
      hospital_type: 'phc',
      address: 'NH-45, Kanchipuram, Tamil Nadu 631501',
      latitude: 12.8342,
      longitude: 79.7036,
      distance_km: 2.4,
      phone: '044-27222250',
      open_24h: false,
      ambulance_108: true,
      pmjay_empanelled: true,
    },
    {
      id: 'demo-hosp-002',
      name: 'Community Health Centre, Chengalpattu',
      hospital_type: 'chc',
      address: 'GST Road, Chengalpattu, Tamil Nadu 603001',
      latitude: 12.6919,
      longitude: 79.9760,
      distance_km: 5.1,
      phone: '044-27422100',
      open_24h: true,
      ambulance_108: true,
      pmjay_empanelled: true,
    },
    {
      id: 'demo-hosp-003',
      name: 'Government District Hospital, Chengalpattu',
      hospital_type: 'district',
      address: 'Hospital Road, Chengalpattu, Tamil Nadu 603001',
      latitude: 12.6960,
      longitude: 79.9800,
      distance_km: 5.6,
      phone: '044-27422200',
      open_24h: true,
      ambulance_108: true,
      pmjay_empanelled: true,
    },
  ],
  total: 3,
  patient_location: { lat: 12.6920, lng: 79.9762, district: 'Chengalpattu' },
};

// ── Teleconsult slots ──────────────────────────────────────────────────────────

export const DEMO_TELECONSULT_SLOTS: TeleconsultSlot[] = [
  {
    doctor_name: 'Dr. Priya Ramachandran',
    specialty: 'General Medicine',
    languages: ['ta', 'en'],
    available_at: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
    platform: 'eSanjeevani',
    booking_url: 'https://esanjeevaniopd.in',
  },
  {
    doctor_name: 'Dr. Arvind Sharma',
    specialty: 'General Medicine',
    languages: ['hi', 'en'],
    available_at: new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString(),
    platform: 'eSanjeevani',
    booking_url: 'https://esanjeevaniopd.in',
  },
];

// ── Voice input ────────────────────────────────────────────────────────────────

export const DEMO_VOICE_RESPONSE: VoiceInputResponse = {
  transcript: 'I have had fever and cough for the past two days with a sore throat.',
  detected_language: 'en',
  confidence: 0.91,
};

// ── Network error detection ────────────────────────────────────────────────────

/** Returns true for errors that mean "backend not reachable at all" */
export function isNetworkUnreachable(err: unknown): boolean {
  if (!err) return false;
  const msg      = String((err as any)?.message  ?? '').toLowerCase();
  const code     = String((err as any)?.code     ?? '').toLowerCase();
  const causeMsg = String((err as any)?.cause?.message ?? '').toLowerCase();
  return (
    msg.includes('network request failed') ||
    msg.includes('econnrefused') ||
    msg.includes('failed to fetch') ||
    msg.includes('network error') ||
    msg.includes('timeout') ||
    causeMsg.includes('econnrefused') ||
    causeMsg.includes('network') ||
    code === 'econnrefused' ||
    code === 'enotfound' ||
    code === 'network_error' ||
    code === 'err_network' ||       // axios on Android
    code === 'econnaborted' ||      // axios request timeout
    code === 'etimedout'
  );
}

// ── Demo mode flag ─────────────────────────────────────────────────────────────
// Set to true the first time a demo fallback is used; never reset to false.
// Read by DemoBanner via useDemoMode hook.
let _isDemoMode = false;
const _listeners: Array<() => void> = [];

export function markDemoMode(): void {
  if (!_isDemoMode) {
    _isDemoMode = true;
    _listeners.forEach((fn) => fn());
  }
}

export function isDemoMode(): boolean {
  return _isDemoMode;
}

export function subscribeDemoMode(fn: () => void): () => void {
  _listeners.push(fn);
  return () => {
    const idx = _listeners.indexOf(fn);
    if (idx !== -1) _listeners.splice(idx, 1);
  };
}
