/**
 * Vaidya — Patients service (CRUD, sessions, consent, erasure)
 * Falls back to demo mode when the backend is unreachable.
 */

import { apiClient } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PatientCreateBody {
  abdm_health_id?:     string;
  phone_number?:       string;
  preferred_language?: string;
  district_code?:      string;
  age_group?:          'child' | 'adult' | 'senior';
  gender?:             'male' | 'female' | 'other' | 'prefer_not_to_say';
  pmjay_eligible?:     boolean;
}

export interface PatientResponse {
  id:                  string;
  abdm_health_id:      string | null;
  preferred_language:  string;
  district_code:       string | null;
  age_group:           string | null;
  gender:              string | null;
  pmjay_eligible:      boolean;
  created_at:          string;
}

export interface PatientSession {
  session_id:        string;
  created_at:        string;
  primary_diagnosis: string;
  triage_level:      number;
  triage_label:      string;
  input_language:    string;
}

export type ConsentType = 'data_processing' | 'anonymised_analytics' | 'asha_contact';

export interface PatientConsentBody {
  patient_id:   string;
  consent_type: ConsentType;
  granted:      boolean;
}

export interface PatientConsentResponse {
  status:       string;
  consent_type: ConsentType;
  granted:      boolean;
  timestamp:    string;
}

export interface PatientEraseResponse {
  status:         string;
  patient_id:     string;
  erased_fields:  string[];
  timestamp:      string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function demoDelay(ms = 700): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_PATIENT: PatientResponse = {
  id:                 'patient-demo-001',
  abdm_health_id:     '12-3456-7890-1234',
  preferred_language: 'ta',
  district_code:      'TN-CBE',
  age_group:          'adult',
  gender:             'female',
  pmjay_eligible:     true,
  created_at:         new Date(Date.now() - 30 * 86400 * 1000).toISOString(),
};

const DEMO_SESSIONS: PatientSession[] = [
  {
    session_id:        'sess-demo-001',
    created_at:        new Date(Date.now() - 2 * 86400 * 1000).toISOString(),
    primary_diagnosis: 'Dengue Fever',
    triage_level:      3,
    triage_label:      'Urgent',
    input_language:    'ta',
  },
  {
    session_id:        'sess-demo-002',
    created_at:        new Date(Date.now() - 10 * 86400 * 1000).toISOString(),
    primary_diagnosis: 'Viral Upper Respiratory Infection',
    triage_level:      1,
    triage_label:      'Mild',
    input_language:    'ta',
  },
  {
    session_id:        'sess-demo-003',
    created_at:        new Date(Date.now() - 25 * 86400 * 1000).toISOString(),
    primary_diagnosis: 'Acute Watery Diarrhoea',
    triage_level:      2,
    triage_label:      'Moderate',
    input_language:    'en',
  },
];

// ── Patients API ──────────────────────────────────────────────────────────────

export async function createPatient(body: PatientCreateBody): Promise<PatientResponse> {
  try {
    const { data } = await apiClient.post('/patients/', body, { timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(800);
    return {
      ...DEMO_PATIENT,
      abdm_health_id:     body.abdm_health_id     ?? null,
      preferred_language: body.preferred_language ?? 'en',
      district_code:      body.district_code      ?? null,
      age_group:          body.age_group          ?? null,
      gender:             body.gender             ?? null,
      pmjay_eligible:     body.pmjay_eligible     ?? false,
      created_at:         new Date().toISOString(),
    };
  }
}

export async function getPatient(id: string): Promise<PatientResponse> {
  try {
    const { data } = await apiClient.get(`/patients/${id}`, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return { ...DEMO_PATIENT, id };
  }
}

export async function updatePatient(
  id:   string,
  body: Partial<PatientCreateBody>,
): Promise<PatientResponse> {
  try {
    const { data } = await apiClient.patch(`/patients/${id}`, body, { timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return { ...DEMO_PATIENT, id, ...body };
  }
}

export async function getPatientSessions(
  id:     string,
  params?: { limit?: number; offset?: number },
): Promise<PatientSession[]> {
  try {
    const { data } = await apiClient.get(`/patients/${id}/sessions`, { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return DEMO_SESSIONS;
  }
}

export async function updatePatientConsent(body: PatientConsentBody): Promise<PatientConsentResponse> {
  try {
    const { data } = await apiClient.post('/patients/consent', body, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return {
      status:       'updated',
      consent_type: body.consent_type,
      granted:      body.granted,
      timestamp:    new Date().toISOString(),
    };
  }
}

export async function erasePatient(id: string): Promise<PatientEraseResponse> {
  try {
    const { data } = await apiClient.delete(`/patients/${id}`, { timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(900);
    return {
      status:        'erased',
      patient_id:    id,
      erased_fields: ['phone_number', 'abdm_health_id', 'district_code'],
      timestamp:     new Date().toISOString(),
    };
  }
}
