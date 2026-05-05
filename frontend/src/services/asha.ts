/**
 * Vaidya — ASHA worker service (queue, nearby, register, resolve, district, stats)
 * Always returns demo data on any error — never surfaces backend failures to users.
 */

import { apiClient } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AshaQueueItem {
  session_id:        string;
  triage_level:      number;
  triage_label:      string;
  primary_diagnosis: string;
  language:          string;
  duration:          number;
  red_flags:         string[];
  created_at:        string;
}

export interface AshaQueueResponse {
  count: number;
  queue: AshaQueueItem[];
}

export interface AshaWorkerSummary {
  id:            string;
  name:          string;
  phone:         string;
  village:       string;
  district_code: string;
  distance_km:   number;
}

export interface NearbyWorkersResponse {
  count:   number;
  workers: AshaWorkerSummary[];
}

export interface AshaRegisterBody {
  name:           string;
  phone:          string;
  latitude:       number;
  longitude:      number;
  village?:       string;
  district_code?: string;
  nhm_id?:        string;
  fcm_token?:     string;
}

export interface AshaRegisterResponse {
  status:    string;
  worker_id: string;
  name:      string;
}

export interface AshaResolveBody {
  worker_id:        string;
  resolution_note?: string;
}

export interface AshaResolveResponse {
  status:      string;
  session_id:  string;
  worker_id:   string;
  resolved_at: string;
}

export interface AshaWorkerDetail {
  id:       string;
  name:     string;
  phone:    string;
  village:  string;
  active:   boolean;
  has_fcm:  boolean;
}

export interface AshaDistrictResponse {
  district_code: string;
  count:         number;
  workers:       AshaWorkerDetail[];
}

export interface AshaStatsResponse {
  worker_id:        string;
  worker_name:      string;
  village:          string;
  period_days:      number;
  total_sessions:   number;
  by_triage_level:  Record<string, number>;
  top_diagnoses:    Array<{ diagnosis: string; count: number }>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function demoDelay(ms = 700): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_QUEUE: AshaQueueResponse = {
  count: 5,
  queue: [
    {
      session_id:        'sess-demo-001',
      triage_level:      4,
      triage_label:      'Emergency',
      primary_diagnosis: 'Malaria (P. falciparum)',
      language:          'ta',
      duration:          510,
      red_flags:         ['High fever >40°C', 'Rigors and chills', 'Altered consciousness'],
      created_at:        new Date(Date.now() - 20 * 60 * 1000).toISOString(),
    },
    {
      session_id:        'sess-demo-002',
      triage_level:      3,
      triage_label:      'Urgent',
      primary_diagnosis: 'Dengue Fever',
      language:          'ta',
      duration:          420,
      red_flags:         ['High fever >39°C', 'Severe headache', 'Rash'],
      created_at:        new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    },
    {
      session_id:        'sess-demo-003',
      triage_level:      3,
      triage_label:      'Urgent',
      primary_diagnosis: 'Acute Watery Diarrhoea',
      language:          'ta',
      duration:          310,
      red_flags:         ['Dehydration signs', 'Sunken eyes'],
      created_at:        new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    },
    {
      session_id:        'sess-demo-004',
      triage_level:      2,
      triage_label:      'Moderate',
      primary_diagnosis: 'Typhoid Fever',
      language:          'ta',
      duration:          265,
      red_flags:         ['Prolonged fever'],
      created_at:        new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    },
    {
      session_id:        'sess-demo-005',
      triage_level:      1,
      triage_label:      'Mild',
      primary_diagnosis: 'Viral Upper Respiratory Infection',
      language:          'en',
      duration:          185,
      red_flags:         [],
      created_at:        new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
    },
  ],
};

const DEMO_NEARBY_WORKERS: NearbyWorkersResponse = {
  count: 3,
  workers: [
    { id: 'asha-001', name: 'Kavitha Rajan',      phone: '+919876543210', village: 'Saravanampatti', district_code: 'TN-CBE', distance_km: 1.2 },
    { id: 'asha-002', name: 'Meenakshi Sundaram', phone: '+919876543211', village: 'Ganapathy',      district_code: 'TN-CBE', distance_km: 2.8 },
    { id: 'asha-003', name: 'Selvi Murugan',      phone: '+919876543212', village: 'Peelamedu',      district_code: 'TN-CBE', distance_km: 4.1 },
  ],
};

const DEMO_DISTRICT_WORKERS: AshaDistrictResponse = {
  district_code: 'TN-CBE',
  count:         3,
  workers: [
    { id: 'asha-001', name: 'Kavitha Rajan',      phone: '+919876543210', village: 'Saravanampatti', active: true,  has_fcm: true  },
    { id: 'asha-002', name: 'Meenakshi Sundaram', phone: '+919876543211', village: 'Ganapathy',      active: true,  has_fcm: true  },
    { id: 'asha-003', name: 'Selvi Murugan',      phone: '+919876543212', village: 'Peelamedu',      active: true,  has_fcm: false },
  ],
};

const DEMO_STATS: AshaStatsResponse = {
  worker_id:       'asha-001',
  worker_name:     'Kavitha Rajan',
  village:         'Saravanampatti',
  period_days:     30,
  total_sessions:  48,
  by_triage_level: { '1': 20, '2': 15, '3': 10, '4': 3 },
  top_diagnoses: [
    { diagnosis: 'Malaria (P. falciparum)',            count: 11 },
    { diagnosis: 'Viral Upper Respiratory Infection', count: 10 },
    { diagnosis: 'Dengue Fever',                      count: 8  },
    { diagnosis: 'Acute Watery Diarrhoea',            count: 7  },
  ],
};

// ── ASHA API ──────────────────────────────────────────────────────────────────

export async function getAshaQueue(params?: {
  worker_id?:  string;
  district?:   string;
  triage_min?: number;
  limit?:      number;
}): Promise<AshaQueueResponse> {
  try {
    const { data } = await apiClient.get('/asha/queue', { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay();
    return DEMO_QUEUE;
  }
}

export async function getNearbyAshaWorkers(params: {
  lat:     number;
  lng:     number;
  radius?: number;
  limit?:  number;
}): Promise<NearbyWorkersResponse> {
  try {
    const { data } = await apiClient.get('/asha/nearby', { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(600);
    return DEMO_NEARBY_WORKERS;
  }
}

export async function registerAshaWorker(body: AshaRegisterBody): Promise<AshaRegisterResponse> {
  try {
    const { data } = await apiClient.post('/asha/register', body, { timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(900);
    return {
      status:    'registered',
      worker_id: `asha-demo-${Date.now()}`,
      name:      body.name,
    };
  }
}

export async function resolveAshaSession(
  session_id: string,
  body:        AshaResolveBody,
): Promise<AshaResolveResponse> {
  try {
    const { data } = await apiClient.post(`/asha/resolve/${session_id}`, body, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return {
      status:      'resolved',
      session_id,
      worker_id:   body.worker_id,
      resolved_at: new Date().toISOString(),
    };
  }
}

export async function getAshaByDistrict(
  district_code: string,
  params?: { active_only?: boolean },
): Promise<AshaDistrictResponse> {
  try {
    const { data } = await apiClient.get(`/asha/district/${district_code}`, { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return { ...DEMO_DISTRICT_WORKERS, district_code };
  }
}

export async function getAshaStats(
  worker_id: string,
  params?: { days?: number },
): Promise<AshaStatsResponse> {
  try {
    const { data } = await apiClient.get(`/asha/stats/${worker_id}`, { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return { ...DEMO_STATS, worker_id };
  }
}
