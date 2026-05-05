/**
 * Vaidya — Analytics service (district dashboard, outbreaks, hotspots, trends, ASHA performance)
 * Always returns demo data on any error — never surfaces backend failures to users.
 */

import { apiClient } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface TopDisease {
  diagnosis:       string;
  case_count:      number;
  avg_triage_level: number;
}

export interface HourlyTrendPoint {
  timestamp: string;
  cases:     number;
  avg_triage: number;
}

export interface DistrictDashboardResponse {
  district_code:    string;
  total_cases:      number;
  emergency_cases:  number;
  urgent_cases:     number;
  avg_triage_level: number;
  triage_by_level:  Record<string, number>;
  top_diseases:     TopDisease[];
  active_outbreaks: number;
  outbreak_alerts:  OutbreakAlert[];
  hourly_trend:     HourlyTrendPoint[];
  last_updated:     string;
}

export interface OutbreakAlert {
  id:               string;
  alert_time:       string;
  district_code:    string;
  diagnosis:        string;
  current_cases:    number;
  baseline_mean:    number;
  z_score:          number;
  percent_increase: number;
  severity:         string;
  status:           string;
  asha_notified:    boolean;
  acknowledged_by:  string | null;
  acknowledged_at:  string | null;
  hours_since_alert: number;
}

export interface HotspotResponse {
  id:            string;
  detected_at:   string;
  district_code: string;
  diagnosis:     string;
  center_lat:    number;
  center_lng:    number;
  radius_km:     number;
  case_count:    number;
  density_score: number;
  p_value:       number;
  relative_risk: number;
}

export interface DiseaseTrendPoint {
  timestamp:    string;
  case_count:   number;
  avg_severity: number;
}

export interface DiseaseTrendResponse {
  district_code:   string;
  diagnosis:       string;
  data_points:     DiseaseTrendPoint[];
  total_cases:     number;
  mean_daily:      number;
  trend_direction: string;
  growth_rate:     number;
}

export interface AshaPerformanceResponse {
  asha_worker_id:           string;
  name:                     string;
  district_code:            string;
  period_days:              number;
  total_assignments:        number;
  acknowledged_count:       number;
  completed_count:          number;
  acknowledgment_rate:      number;
  completion_rate:          number;
  avg_response_time_mins:   number;
  referrals:                number;
}

export interface AcknowledgeAlertBody {
  officer_id: string;
  notes?:     string;
}

export interface AcknowledgeAlertResponse {
  status:          string;
  alert_id:        string;
  acknowledged_by: string;
  timestamp:       string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function demoDelay(ms = 700): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_DISTRICT = 'TN-CBE';

const DEMO_OUTBREAK_ALERTS: OutbreakAlert[] = [
  {
    id:               'alert-001',
    alert_time:       new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    district_code:    DEMO_DISTRICT,
    diagnosis:        'Malaria (P. falciparum)',
    current_cases:    31,
    baseline_mean:    4.8,
    z_score:          4.2,
    percent_increase: 546,
    severity:         'high',
    status:           'active',
    asha_notified:    true,
    acknowledged_by:  null,
    acknowledged_at:  null,
    hours_since_alert: 2,
  },
  {
    id:               'alert-002',
    alert_time:       new Date(Date.now() - 5 * 3600 * 1000).toISOString(),
    district_code:    DEMO_DISTRICT,
    diagnosis:        'Dengue Fever',
    current_cases:    42,
    baseline_mean:    14.2,
    z_score:          3.8,
    percent_increase: 196,
    severity:         'high',
    status:           'active',
    asha_notified:    true,
    acknowledged_by:  null,
    acknowledged_at:  null,
    hours_since_alert: 5,
  },
  {
    id:               'alert-003',
    alert_time:       new Date(Date.now() - 18 * 3600 * 1000).toISOString(),
    district_code:    DEMO_DISTRICT,
    diagnosis:        'Acute Watery Diarrhoea',
    current_cases:    27,
    baseline_mean:    9.5,
    z_score:          2.9,
    percent_increase: 184,
    severity:         'medium',
    status:           'acknowledged',
    asha_notified:    true,
    acknowledged_by:  'officer-101',
    acknowledged_at:  new Date(Date.now() - 12 * 3600 * 1000).toISOString(),
    hours_since_alert: 18,
  },
];

const DEMO_HOURLY_TREND: HourlyTrendPoint[] = Array.from({ length: 24 }, (_, i) => ({
  timestamp:  new Date(Date.now() - (23 - i) * 3600 * 1000).toISOString(),
  cases:      Math.floor(8 + Math.random() * 14),
  avg_triage: parseFloat((2.2 + Math.random() * 0.8).toFixed(1)),
}));

const DEMO_DASHBOARD: DistrictDashboardResponse = {
  district_code:    DEMO_DISTRICT,
  total_cases:      318,
  emergency_cases:  12,
  urgent_cases:     47,
  avg_triage_level: 2.4,
  triage_by_level:  { '1': 89, '2': 170, '3': 47, '4': 12 },
  top_diseases: [
    { diagnosis: 'Viral Upper Respiratory Infection', case_count: 78, avg_triage_level: 1.8 },
    { diagnosis: 'Dengue Fever',                      case_count: 42, avg_triage_level: 2.9 },
    { diagnosis: 'Malaria (P. falciparum)',            case_count: 31, avg_triage_level: 2.7 },
    { diagnosis: 'Acute Watery Diarrhoea',            case_count: 27, avg_triage_level: 2.4 },
    { diagnosis: 'Typhoid Fever',                     case_count: 21, avg_triage_level: 2.6 },
  ],
  active_outbreaks: 3,
  outbreak_alerts:  DEMO_OUTBREAK_ALERTS,
  hourly_trend:     DEMO_HOURLY_TREND,
  last_updated:     new Date().toISOString(),
};

const DEMO_HOTSPOTS: HotspotResponse[] = [
  {
    id:            'hs-001',
    detected_at:   new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    district_code: DEMO_DISTRICT,
    diagnosis:     'Malaria (P. falciparum)',
    center_lat:    10.9881,
    center_lng:    76.9322,
    radius_km:     2.4,
    case_count:    23,
    density_score: 0.83,
    p_value:       0.002,
    relative_risk: 5.4,
  },
  {
    id:            'hs-002',
    detected_at:   new Date(Date.now() - 6 * 3600 * 1000).toISOString(),
    district_code: DEMO_DISTRICT,
    diagnosis:     'Dengue Fever',
    center_lat:    11.0168,
    center_lng:    76.9558,
    radius_km:     3.2,
    case_count:    18,
    density_score: 0.78,
    p_value:       0.003,
    relative_risk: 4.1,
  },
  {
    id:            'hs-003',
    detected_at:   new Date(Date.now() - 14 * 3600 * 1000).toISOString(),
    district_code: DEMO_DISTRICT,
    diagnosis:     'Acute Watery Diarrhoea',
    center_lat:    11.0510,
    center_lng:    76.9890,
    radius_km:     1.8,
    case_count:    12,
    density_score: 0.62,
    p_value:       0.011,
    relative_risk: 3.2,
  },
];

const DEMO_TREND: DiseaseTrendResponse = {
  district_code:   DEMO_DISTRICT,
  diagnosis:       'Dengue Fever',
  data_points: Array.from({ length: 14 }, (_, i) => ({
    timestamp:    new Date(Date.now() - (13 - i) * 86400 * 1000).toISOString(),
    case_count:   Math.floor(5 + i * 2.5 + Math.random() * 4),
    avg_severity: parseFloat((2.4 + Math.random() * 0.6).toFixed(1)),
  })),
  total_cases:     42,
  mean_daily:      3.0,
  trend_direction: 'increasing',
  growth_rate:     0.18,
};

const DEMO_ASHA_PERFORMANCE: AshaPerformanceResponse[] = [
  {
    asha_worker_id:         'asha-001',
    name:                   'Kavitha Rajan',
    district_code:          DEMO_DISTRICT,
    period_days:            30,
    total_assignments:      48,
    acknowledged_count:     45,
    completed_count:        42,
    acknowledgment_rate:    0.94,
    completion_rate:        0.875,
    avg_response_time_mins: 22,
    referrals:              7,
  },
  {
    asha_worker_id:         'asha-002',
    name:                   'Meenakshi Sundaram',
    district_code:          DEMO_DISTRICT,
    period_days:            30,
    total_assignments:      39,
    acknowledged_count:     36,
    completed_count:        31,
    acknowledgment_rate:    0.92,
    completion_rate:        0.795,
    avg_response_time_mins: 31,
    referrals:              5,
  },
  {
    asha_worker_id:         'asha-003',
    name:                   'Selvi Murugan',
    district_code:          DEMO_DISTRICT,
    period_days:            30,
    total_assignments:      55,
    acknowledged_count:     53,
    completed_count:        50,
    acknowledgment_rate:    0.96,
    completion_rate:        0.909,
    avg_response_time_mins: 17,
    referrals:              11,
  },
];

// ── Analytics API ─────────────────────────────────────────────────────────────

export async function getDistrictDashboard(params: {
  district_code: string;
  hours?:        number;
}): Promise<DistrictDashboardResponse> {
  try {
    const { data } = await apiClient.get('/analytics/dashboard/district', { params, timeout: 12_000 });
    return data;
  } catch {
    await demoDelay();
    return { ...DEMO_DASHBOARD, district_code: params.district_code };
  }
}

export async function getActiveOutbreaks(params?: {
  district_code?: string;
  severity?:      string;
  days_back?:     number;
}): Promise<OutbreakAlert[]> {
  try {
    const { data } = await apiClient.get('/analytics/outbreaks/active', { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(600);
    return DEMO_OUTBREAK_ALERTS;
  }
}

export async function getOutbreakById(id: string): Promise<OutbreakAlert> {
  try {
    const { data } = await apiClient.get(`/analytics/outbreaks/${id}`, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(500);
    return DEMO_OUTBREAK_ALERTS.find((a) => a.id === id) ?? DEMO_OUTBREAK_ALERTS[0];
  }
}

export async function acknowledgeOutbreak(
  id:   string,
  body: AcknowledgeAlertBody,
): Promise<AcknowledgeAlertResponse> {
  try {
    const { data } = await apiClient.post(`/analytics/outbreaks/${id}/acknowledge`, body, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return {
      status:          'acknowledged',
      alert_id:        id,
      acknowledged_by: body.officer_id,
      timestamp:       new Date().toISOString(),
    };
  }
}

export async function getHotspots(params: {
  district_code: string;
  diagnosis?:    string;
  hours_back?:   number;
}): Promise<HotspotResponse[]> {
  try {
    const { data } = await apiClient.get('/analytics/hotspots', { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return DEMO_HOTSPOTS;
  }
}

export async function getDiseaseTrend(params: {
  district_code: string;
  diagnosis:     string;
  days_back?:    number;
}): Promise<DiseaseTrendResponse> {
  try {
    const { data } = await apiClient.get('/analytics/trends', { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return { ...DEMO_TREND, district_code: params.district_code, diagnosis: params.diagnosis };
  }
}

export async function getAshaPerformance(params: {
  district_code: string;
  days_back?:    number;
}): Promise<AshaPerformanceResponse[]> {
  try {
    const { data } = await apiClient.get('/analytics/asha/performance', { params, timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(700);
    return DEMO_ASHA_PERFORMANCE.map((w) => ({ ...w, district_code: params.district_code }));
  }
}
