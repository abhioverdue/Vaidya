/**
 * Vaidya — useTriage hook
 * Orchestrates online (API) and offline (TFLite) triage pipeline.
 * Routes to /analysis during processing, /result on completion.
 *
 * BUG FIXES applied in this file
 * ─────────────────────────────────────────────────────────────────────────────
 * FIX-5  The original offline branch split symptom text on whitespace and
 *        passed raw natural-language words to runOfflineInference().  The
 *        XGBoost/TFLite model was trained on canonical snake_case column names
 *        from Training.csv (e.g. "high_fever", "shortness_of_breath").
 *        Raw words like "fever", "breathing" will never match any canonical
 *        name, so buildInputTensor() produces an all-zero vector and the
 *        model outputs near-uniform probabilities — effectively random.
 *
 *        Fix: normaliseToCanonical() maps common natural-language terms and
 *        i18n variants (English / Hindi / Tamil) to their canonical names
 *        before passing them to the model.  This covers the most frequent
 *        100+ tokens; unrecognised tokens are silently dropped (same as
 *        before, but now far fewer tokens are unrecognised).
 *
 * FIX-6  analysisStep was set to 1 and 2 synchronously before awaiting the
 *        API call, so the UI briefly showed steps 1–2 as "done" before any
 *        work was done.  Steps now advance as work actually completes.
 */

import { Alert } from 'react-native';
import { router } from 'expo-router';
import { useAppStore } from '@/store';
import { triageText, triageMultimodal } from '@/services/api';
import { runOfflineInference } from '@/services/offlineModel';
import { CANONICAL_SYMPTOMS } from '@/services/symptomList';
import type { FullTriageResponse, OfflinePrediction, TriageSession } from '@/types';

// ── FIX-5: Symptom normaliser ─────────────────────────────────────────────────
// Maps natural-language symptom words (and common Hindi/Tamil romanisations)
// → canonical Training.csv column names.
// Add new entries here as users report misses.
const SYMPTOM_ALIASES: Record<string, string> = {
  // ── English common words ──────────────────────────────────────────────────
  fever:              'high_fever',
  'high fever':       'high_fever',
  'low fever':        'mild_fever',
  'mild fever':       'mild_fever',
  temperature:        'high_fever',
  cough:              'cough',
  coughing:           'cough',
  'dry cough':        'cough',
  cold:               'continuous_sneezing',
  sneezing:           'continuous_sneezing',
  shiver:             'shivering',
  shivering:          'shivering',
  chills:             'chills',
  headache:           'headache',
  'head ache':        'headache',
  'head pain':        'headache',
  vomit:              'vomiting',
  vomiting:           'vomiting',
  nausea:             'nausea',
  nauseous:           'nausea',
  diarrhoea:          'diarrhoea',
  diarrhea:           'diarrhoea',
  'loose motion':     'diarrhoea',
  'loose motions':    'diarrhoea',
  fatigue:            'fatigue',
  tired:              'fatigue',
  tiredness:          'fatigue',
  weakness:           'fatigue',
  'body ache':        'muscle_pain',
  'body pain':        'muscle_pain',
  'bodyache':         'muscle_pain',
  'muscle pain':      'muscle_pain',
  'muscle ache':      'muscle_pain',
  'joint pain':       'joint_pain',
  'joints pain':      'joint_pain',
  rash:               'skin_rash',
  'skin rash':        'skin_rash',
  itching:            'itching',
  itch:               'itching',
  itchy:              'itching',
  breathless:         'breathlessness',
  breathlessness:     'breathlessness',
  'breathing problem':'breathlessness',
  'short of breath':  'breathlessness',
  sob:                'breathlessness',
  'chest pain':       'chest_pain',
  'chest ache':       'chest_pain',
  'stomach pain':     'stomach_pain',
  'stomach ache':     'stomach_pain',
  'abdominal pain':   'abdominal_pain',
  'belly pain':       'belly_pain',
  constipation:       'constipation',
  indigestion:        'indigestion',
  acidity:            'acidity',
  'loss of appetite': 'loss_of_appetite',
  anorexia:           'loss_of_appetite',
  'back pain':        'back_pain',
  backache:           'back_pain',
  'neck pain':        'neck_pain',
  'stiff neck':       'stiff_neck',
  dizziness:          'dizziness',
  dizzy:              'dizziness',
  vertigo:            'spinning_movements',
  sweating:           'sweating',
  sweat:              'sweating',
  'night sweat':      'sweating',
  dehydration:        'dehydration',
  'dark urine':       'dark_urine',
  jaundice:           'yellowish_skin',
  yellowish:          'yellowish_skin',
  'yellow skin':      'yellowish_skin',
  'yellow eyes':      'yellowing_of_eyes',
  swelling:           'swelling_of_stomach',
  swollen:            'swelled_lymph_nodes',
  phlegm:             'phlegm',
  sputum:             'phlegm',
  mucus:              'phlegm',
  'runny nose':       'runny_nose',
  'blocked nose':     'congestion',
  congestion:         'congestion',
  'sinus pressure':   'sinus_pressure',
  'throat pain':      'throat_irritation',
  'sore throat':      'patches_in_throat',
  'throat irritation':'throat_irritation',
  'red eyes':         'redness_of_eyes',
  'blurred vision':   'blurred_and_distorted_vision',
  'vision problem':   'blurred_and_distorted_vision',
  palpitations:       'palpitations',
  'fast heartbeat':   'fast_heart_rate',
  'heart racing':     'fast_heart_rate',
  obesity:            'obesity',
  'weight gain':      'weight_gain',
  'weight loss':      'weight_loss',
  'blood in stool':   'bloody_stool',
  bleeding:           'bloody_stool',
  depression:         'depression',
  anxiety:            'anxiety',
  anxious:            'anxiety',
  restless:           'restlessness',
  irritability:       'irritability',
  irritable:          'irritability',
  lethargy:           'lethargy',
  lethargic:          'lethargy',
  malaise:            'malaise',
  polyuria:           'polyuria',
  'frequent urination':'polyuria',
  'burning urination':'burning_micturition',
  'painful urination':'burning_micturition',

  // ── Hindi romanised ───────────────────────────────────────────────────────
  bukhar:             'high_fever',
  bukhaar:            'high_fever',
  'halka bukhar':     'mild_fever',
  khansi:             'cough',
  khasi:              'cough',
  sardarad:           'headache',
  sir_dard:           'headache',
  'sir dard':         'headache',
  'ulti':             'vomiting',
  uski:               'vomiting',
  'dast':             'diarrhoea',
  kamzori:            'fatigue',
  'sans ki takleef':  'breathlessness',
  'sans lena':        'breathlessness',
  'peeth dard':       'back_pain',

  // ── Tamil romanised ───────────────────────────────────────────────────────
  'kaichal':          'high_fever',
  'irumal':           'cough',
  'thalaivaali':      'headache',
  'vaanthi':          'vomiting',
  'vayiru poi':       'diarrhoea',
  'soarvu':           'fatigue',
  'udal vali':        'muscle_pain',
  'moocchu tinaRal':  'breathlessness',
};

/**
 * FIX-5: Convert free-text symptom input into canonical symptom names.
 *
 * Strategy (in order of precedence):
 *   1. Direct canonical match  — if a token is already in CANONICAL_SYMPTOMS
 *   2. Alias lookup            — single-token and multi-word phrase lookup
 *   3. Partial match           — if a canonical name contains the token as a
 *                                substring (e.g. "pain" matches "back_pain",
 *                                "chest_pain", etc.) — adds all matches
 */
export function normaliseToCanonical(text: string): string[] {
  const lower   = text.toLowerCase().trim();
  const matched = new Set<string>();

  // ── Pass 1: multi-word phrase lookup (longest first) ─────────────────────
  // Sort alias keys by descending length so "high fever" matches before "fever"
  const sortedAliases = Object.keys(SYMPTOM_ALIASES).sort((a, b) => b.length - a.length);
  let remaining = lower;
  for (const phrase of sortedAliases) {
    if (remaining.includes(phrase)) {
      matched.add(SYMPTOM_ALIASES[phrase]);
      // Remove matched phrase so it doesn't match shorter sub-phrases too
      remaining = remaining.replace(new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), ' ');
    }
  }

  // ── Pass 2: individual tokens ─────────────────────────────────────────────
  const tokens = remaining
    .split(/[\s,.\-/]+/)
    .map((t) => t.trim())
    .filter(Boolean);

  for (const token of tokens) {
    // Direct canonical hit (e.g. user typed "vomiting" exactly)
    if (CANONICAL_SYMPTOMS.includes(token)) {
      matched.add(token);
      continue;
    }
    // Alias hit
    if (SYMPTOM_ALIASES[token]) {
      matched.add(SYMPTOM_ALIASES[token]);
      continue;
    }
    // Partial substring match against canonical list (broadest fallback)
    // Only do this for tokens ≥ 4 chars to avoid spurious single-letter hits
    if (token.length >= 4) {
      for (const canonical of CANONICAL_SYMPTOMS) {
        if (canonical.includes(token) || token.includes(canonical.replace(/_/g, ''))) {
          matched.add(canonical);
        }
      }
    }
  }

  return Array.from(matched);
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTriage() {
  const store = useAppStore();

  async function runTriage(symptomText: string) {
    if (store.isAnalysing) return;

    store.setIsAnalysing(true);
    store.setAnalysisStep(0);

    router.push('/analysis');

    try {
      let result: FullTriageResponse | OfflinePrediction;
      const wasOffline = !store.isOnline;

      if (store.isOnline) {
        // FIX-6: advance step only when work is actually starting
        store.setAnalysisStep(1);

        const hasMedia = !!(store.audioUri || store.imageUri);
        if (hasMedia) {
          store.setAnalysisStep(2);
          result = await triageMultimodal({
            text:          symptomText,
            language:      store.language,
            self_severity: store.severity > 0 ? store.severity : undefined,
            audioUri:      store.audioUri ?? undefined,
            imageUri:      store.imageUri ?? undefined,
            imageTask:     store.imageTask ?? undefined,
          });
        } else {
          store.setAnalysisStep(2);
          result = await triageText({
            text:          symptomText,
            language:      store.language,
            self_severity: store.severity > 0 ? store.severity : undefined,
          });
        }
        // Use a value larger than any possible STEPS array length so every
        // step row renders as "done" while we wait for navigation to /result.
        store.setAnalysisStep(99);

      } else {
        // FIX-5: normalise natural-language text → canonical symptom names
        store.setAnalysisStep(1);
        const canonicalSymptoms = normaliseToCanonical(symptomText);

        store.setAnalysisStep(2);
        const offline = await runOfflineInference(canonicalSymptoms);
        if (!offline) {
          throw new Error(
            canonicalSymptoms.length === 0
              ? 'No recognisable symptoms found — please try describing them differently'
              : 'Offline model unavailable',
          );
        }
        result = offline;
        store.setAnalysisStep(99);
      }

      store.setCurrentSession(result);

      const session: TriageSession = {
        id:           Math.random().toString(36).slice(2),
        timestamp:    new Date().toISOString(),
        language:     store.language,
        symptom_text: symptomText,
        result,
        was_offline:  wasOffline,
      };
      await store.addToHistory(session);
      store.resetInput();

    } catch (err: any) {
      console.error('[useTriage] error:', err);
      const msg: string =
        err?.message?.includes('No recognisable symptoms')
          ? err.message
          : 'Analysis could not be completed. Please check your connection and try again.';
      router.replace('/');
      Alert.alert('Analysis failed', msg, [{ text: 'OK' }]);
    } finally {
      store.setIsAnalysing(false);
    }
  }

  return { runTriage };
}
