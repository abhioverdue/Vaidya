// Vaidya — shared TypeScript types
// Mirrors backend schemas.py exactly — keep in sync with API changes

export type Language = 'en' | 'hi' | 'ta';
export type AgeGroup = 'child' | 'adult' | 'senior';
export type Gender = 'male' | 'female' | 'other' | 'undisclosed';
export type TriageLevel = 1 | 2 | 3 | 4 | 5;
export type DiagnosisSource = 'xgboost' | 'fusion' | 'llm_fallback' | 'llm_gemini';
export type HospitalType = 'phc' | 'chc' | 'district' | 'private' | 'esic' | 'other';

// ── NLP ───────────────────────────────────────────────────────────────────────

export interface ExtractedSymptoms {
  symptoms: string[];
  duration: string | null;
  severity_estimate: number | null;
  body_parts: string[];
  raw_keywords: string[];
}

export interface SymptomVectorResponse {
  extracted: ExtractedSymptoms;
  symptom_vector: Record<string, number>;
  matched_count: number;
  unmatched_terms: string[];
}

// ── Diagnosis ─────────────────────────────────────────────────────────────────

export interface DifferentialEntry {
  disease: string;
  confidence: number;
  confidence_label: 'High' | 'Medium' | 'Low';
}

export interface DiagnosisResult {
  primary_diagnosis: string;
  confidence: number;
  differential: DifferentialEntry[];
  diagnosis_source: DiagnosisSource;
  red_flags: string[];
  description?: string;
  precautions: string[];
  // LLM-enriched fields (present when diagnosis_source === 'llm_gemini')
  icd_hint?: string | null;
  triage_level?: number | null;
  triage_reasoning?: string | null;
  when_to_seek_emergency?: string | null;
  confidence_reason?: string | null;
  // Gemini plain-language health guide (present for all online diagnoses)
  gemini_explanation?: string | null;
  disclaimer: string;
}

export interface TriageResponse {
  level: TriageLevel;
  label: string;
  reasoning: string;
  asha_assigned?: {
    name: string;
    phone: string;
    village?: string;
    distance_km: number;
  } | null;
  follow_up_at?: string | null;
}

export interface FullTriageResponse {
  session_id: string;
  input_language: Language;
  extracted: ExtractedSymptoms;
  diagnosis: DiagnosisResult;
  triage: TriageResponse;
  audio_result?: any;
  vision_result?: any;
  fusion_weights?: Record<string, number>;
  created_at: string;
}

// ── Voice ─────────────────────────────────────────────────────────────────────

export interface VoiceInputResponse {
  transcript: string;
  detected_language: Language;
  confidence: number;
}

// ── Care ──────────────────────────────────────────────────────────────────────

export interface HospitalResult {
  id: string;
  name: string;
  hospital_type: HospitalType;
  address?: string;
  distance_km: number;
  phone?: string;
  ambulance_108: boolean;
  open_24h: boolean;
  pmjay_empanelled: boolean;
  latitude: number;
  longitude: number;
}

export interface HospitalListResponse {
  results: HospitalResult[];
  total: number;
  patient_location: { lat: number; lng: number; district: string };
}

export interface TeleconsultSlot {
  doctor_name: string;
  specialty: string;
  languages: Language[];
  available_at: string;
  platform: string;
  booking_url?: string;
}

// ── Offline TFLite ────────────────────────────────────────────────────────────

export interface OfflinePrediction {
  primary_diagnosis: string;
  confidence: number;
  differential: { disease: string; confidence: number }[];
  source: 'tflite_offline';
  diagnosis_source?: string;
}

// ── App-level session ─────────────────────────────────────────────────────────

export interface TriageSession {
  id: string;
  timestamp: string;
  language: Language;
  symptom_text: string;
  result: FullTriageResponse | OfflinePrediction;
  was_offline: boolean;
}

// ── API errors ────────────────────────────────────────────────────────────────

export interface ApiError {
  code: string;
  message: string;
  field?: string;
}
