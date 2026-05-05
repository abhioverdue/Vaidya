/**
 * Vaidya — Consent service (descriptions, grant, revoke, status, audit)
 * Falls back to demo mode when the backend is unreachable.
 */

import { apiClient } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ConsentPurpose {
  type:        string;
  required:    boolean;
  description: string;
}

export interface ConsentDescriptionsResponse {
  policy_version: string;
  language:       string;
  purposes:       ConsentPurpose[];
}

export interface ConsentGrantBody {
  patient_id:      string;
  consent_types:   string[];
  policy_version?: string;
  language?:       string;
}

export interface ConsentGrantResponse {
  granted:        string[];
  policy_version: string;
  timestamp:      string;
  message:        string;
}

export interface ConsentRevokeBody {
  patient_id:   string;
  consent_type: string;
  reason?:      string;
}

export interface ConsentRevokeResponse {
  revoked:   string;
  timestamp: string;
  message:   string;
}

export interface ConsentRecord {
  consent_type: string;
  granted:      boolean;
  version:      string;
  timestamp:    string;
}

export interface ConsentStatusResponse {
  patient_id:           string;
  consents:             ConsentRecord[];
  has_required_consent: boolean;
  evaluated_at:         string;
}

export interface ConsentAuditEntry {
  id:           string;
  consent_type: string;
  granted:      boolean;
  version:      string;
  timestamp:    string;
  ip_hash:      string;
}

export interface ConsentAuditResponse {
  patient_id: string;
  entries:    ConsentAuditEntry[];
  total:      number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function demoDelay(ms = 600): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_POLICY_VERSION = '1.2.0';

const DEMO_DESCRIPTIONS: ConsentDescriptionsResponse = {
  policy_version: DEMO_POLICY_VERSION,
  language:       'en',
  purposes: [
    {
      type:        'data_processing',
      required:    true,
      description: 'We process your health information to provide symptom triage and medical guidance. This data is stored securely and never sold to third parties.',
    },
    {
      type:        'anonymised_analytics',
      required:    false,
      description: 'Anonymised, non-identifiable health data helps detect disease outbreaks early and improve public health response in your district.',
    },
    {
      type:        'asha_contact',
      required:    false,
      description: 'Allow your local ASHA (Accredited Social Health Activist) worker to follow up with you for urgent or serious health concerns.',
    },
  ],
};

const DEMO_CONSENTS: ConsentRecord[] = [
  { consent_type: 'data_processing',      granted: true,  version: DEMO_POLICY_VERSION, timestamp: new Date(Date.now() - 30 * 86400 * 1000).toISOString() },
  { consent_type: 'anonymised_analytics', granted: true,  version: DEMO_POLICY_VERSION, timestamp: new Date(Date.now() - 30 * 86400 * 1000).toISOString() },
  { consent_type: 'asha_contact',         granted: false, version: DEMO_POLICY_VERSION, timestamp: new Date(Date.now() - 30 * 86400 * 1000).toISOString() },
];

const DEMO_AUDIT_ENTRIES: ConsentAuditEntry[] = [
  { id: 'audit-001', consent_type: 'data_processing',      granted: true,  version: DEMO_POLICY_VERSION, timestamp: new Date(Date.now() - 30 * 86400 * 1000).toISOString(), ip_hash: 'a3f8c2d1' },
  { id: 'audit-002', consent_type: 'anonymised_analytics', granted: true,  version: DEMO_POLICY_VERSION, timestamp: new Date(Date.now() - 30 * 86400 * 1000).toISOString(), ip_hash: 'a3f8c2d1' },
  { id: 'audit-003', consent_type: 'asha_contact',         granted: false, version: DEMO_POLICY_VERSION, timestamp: new Date(Date.now() - 30 * 86400 * 1000).toISOString(), ip_hash: 'a3f8c2d1' },
];

// ── Consent API ───────────────────────────────────────────────────────────────

export async function getConsentDescriptions(params?: {
  language?: string;
}): Promise<ConsentDescriptionsResponse> {
  try {
    const { data } = await apiClient.get('/consent/descriptions', { params, timeout: 8_000 });
    return data;
  } catch {
    await demoDelay();
    return { ...DEMO_DESCRIPTIONS, language: params?.language ?? 'en' };
  }
}

export async function grantConsent(body: ConsentGrantBody): Promise<ConsentGrantResponse> {
  try {
    const { data } = await apiClient.post('/consent/grant', body, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(700);
    return {
      granted:        body.consent_types,
      policy_version: body.policy_version ?? DEMO_POLICY_VERSION,
      timestamp:      new Date().toISOString(),
      message:        'Consent recorded successfully.',
    };
  }
}

export async function revokeConsent(body: ConsentRevokeBody): Promise<ConsentRevokeResponse> {
  try {
    const { data } = await apiClient.post('/consent/revoke', body, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(700);
    return {
      revoked:   body.consent_type,
      timestamp: new Date().toISOString(),
      message:   'Consent revoked. Your data preferences have been updated.',
    };
  }
}

export async function getConsentStatus(patient_id: string): Promise<ConsentStatusResponse> {
  try {
    const { data } = await apiClient.get(`/consent/status/${patient_id}`, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return {
      patient_id,
      consents:             DEMO_CONSENTS,
      has_required_consent: true,
      evaluated_at:         new Date().toISOString(),
    };
  }
}

export async function getConsentAudit(patient_id: string): Promise<ConsentAuditResponse> {
  try {
    const { data } = await apiClient.get(`/consent/audit/${patient_id}`, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(700);
    return {
      patient_id,
      entries: DEMO_AUDIT_ENTRIES,
      total:   DEMO_AUDIT_ENTRIES.length,
    };
  }
}
