/**
 * Vaidya — NLP service (symptom extraction, symptom list, search)
 * Falls back to demo mode when the backend is unreachable.
 */

import { apiClient } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface NlpExtractBody {
  text:      string;
  language?: string;
}

export interface NlpExtractResponse {
  symptoms:          string[];
  duration?:         string;
  severity_estimate?: number;
  body_parts?:       string[];
}

export interface SymptomEntry {
  id:      string;
  name:    string;
  aliases: string[];
}

export interface SymptomsListResponse {
  symptoms: SymptomEntry[];
}

export interface SymptomSearchResult {
  id:    string;
  name:  string;
  score: number;
}

export interface SymptomSearchResponse {
  results: SymptomSearchResult[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function demoDelay(ms = 600): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_SYMPTOMS: SymptomEntry[] = [
  { id: 'sym-001', name: 'fever',           aliases: ['high temperature', 'pyrexia', 'bukhar', 'jvara'] },
  { id: 'sym-002', name: 'cough',           aliases: ['dry cough', 'wet cough', 'khansi', 'kasi'] },
  { id: 'sym-003', name: 'headache',        aliases: ['head pain', 'migraine', 'sir dard', 'talaival vaali'] },
  { id: 'sym-004', name: 'body ache',       aliases: ['myalgia', 'muscle pain', 'badan dard', 'udal vaali'] },
  { id: 'sym-005', name: 'nausea',          aliases: ['feeling sick', 'ji machlana', 'vanthi unarvu'] },
  { id: 'sym-006', name: 'vomiting',        aliases: ['emesis', 'ulti', 'vomit', 'vanthi'] },
  { id: 'sym-007', name: 'diarrhoea',       aliases: ['loose motions', 'loose stools', 'dast', 'vayitru ponukku'] },
  { id: 'sym-008', name: 'chest pain',      aliases: ['chest tightness', 'seene mein dard', 'maarbil vaali'] },
  { id: 'sym-009', name: 'breathlessness',  aliases: ['shortness of breath', 'dyspnoea', 'sans lena', 'maoochu tiranaippu'] },
  { id: 'sym-010', name: 'rash',            aliases: ['skin rash', 'eruption', 'chamdi par daane', 'soriyaval'] },
  { id: 'sym-011', name: 'joint pain',      aliases: ['arthralgia', 'jodo mein dard', 'meerppu vaali'] },
  { id: 'sym-012', name: 'abdominal pain',  aliases: ['stomach pain', 'pet dard', 'vayitru vaali'] },
  { id: 'sym-013', name: 'sore throat',     aliases: ['throat pain', 'gale mein dard', 'tondai vaali'] },
  { id: 'sym-014', name: 'runny nose',      aliases: ['nasal discharge', 'naak bahna', 'mooku othukkal'] },
  { id: 'sym-015', name: 'fatigue',         aliases: ['weakness', 'tiredness', 'kamzori', 'soru'] },
];

// ── NLP API ───────────────────────────────────────────────────────────────────

export async function extractSymptoms(body: NlpExtractBody): Promise<NlpExtractResponse> {
  try {
    const { data } = await apiClient.post('/nlp/extract', body, { timeout: 10_000 });
    return data;
  } catch {
    await demoDelay(800);
    return {
      symptoms:          ['fever', 'headache', 'body ache'],
      duration:          '2 days',
      severity_estimate: 4,
      body_parts:        ['head', 'body'],
    };
  }
}

export async function getSymptomsList(): Promise<SymptomsListResponse> {
  try {
    const { data } = await apiClient.get('/nlp/symptoms', { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(500);
    return { symptoms: DEMO_SYMPTOMS };
  }
}

export async function searchSymptoms(params: {
  q:         string;
  language?: string;
}): Promise<SymptomSearchResponse> {
  try {
    const { data } = await apiClient.get('/nlp/symptoms/search', { params, timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(400);
    const q = params.q.toLowerCase();
    const matched = DEMO_SYMPTOMS
      .filter((s) => s.name.includes(q) || s.aliases.some((a) => a.includes(q)))
      .map((s) => ({ id: s.id, name: s.name, score: s.name.startsWith(q) ? 1.0 : 0.7 }))
      .slice(0, 5);
    return { results: matched.length ? matched : [{ id: 'sym-001', name: 'fever', score: 0.5 }] };
  }
}
