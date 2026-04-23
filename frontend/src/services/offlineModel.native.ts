/**
 * Vaidya — Offline symptom classifier (native: Android / iOS)
 *
 * Uses onnxruntime-react-native to run the XGBoost ONNX model on-device.
 * No tfjs, no URL.createObjectURL, no Hermes crashes.
 *
 * Input:  Float32[1, N_SYMPTOMS] — binary symptom presence vector
 * Output: Float32[1, N_CLASSES]  — softmax probabilities per disease class
 */

import { Asset } from 'expo-asset';
import * as FileSystem from 'expo-file-system';
import * as ort from 'onnxruntime-react-native';

import { CANONICAL_SYMPTOMS } from './symptomList';
import { MIN_SYMPTOMS_FOR_TFLITE } from '@/constants';
import type { OfflinePrediction } from '@/types';

let session: ort.InferenceSession | null = null;
let diseaseLabels: string[]              = [];
let loadAttempted                        = false;
let loadError: string | null            = null;

export async function loadOfflineModel(): Promise<boolean> {
  if (session !== null) return true;
  if (loadAttempted) return false;

  loadAttempted = true;
  loadError     = null;

  try {
    const modelAsset = Asset.fromModule(
      require('../assets/models/vaidya_symptom_classifier.onnx'),
    );
    await modelAsset.downloadAsync();

    if (!modelAsset.localUri) throw new Error('Model asset has no localUri after download');

    // expo-asset returns a file:// URI; ONNX Runtime needs a plain FS path
    const localPath = modelAsset.localUri.startsWith('file://')
      ? modelAsset.localUri.slice(7)
      : modelAsset.localUri;

    diseaseLabels = require('../assets/models/disease_labels.json') as string[];
    session = await ort.InferenceSession.create(localPath, {
      executionProviders: ['cpu'],
    });
    return true;
  } catch (err) {
    loadError = String(err);
    console.warn('[Vaidya] Offline ONNX model load failed:', err);
    return false;
  }
}

export function isModelReady(): boolean {
  return session !== null && diseaseLabels.length > 0;
}

export function getModelLoadError(): string | null {
  return loadError;
}

export async function runOfflineInference(
  symptoms: string[],
): Promise<OfflinePrediction | null> {
  if (!isModelReady()) {
    const loaded = await loadOfflineModel();
    if (!loaded) return null;
  }

  if (symptoms.length < MIN_SYMPTOMS_FOR_TFLITE) return null;

  try {
    // Build binary symptom vector
    const vec = new Float32Array(CANONICAL_SYMPTOMS.length).fill(0);
    for (const sym of symptoms) {
      const idx = CANONICAL_SYMPTOMS.indexOf(sym);
      if (idx !== -1) vec[idx] = 1.0;
    }

    const inputName = session!.inputNames[0];
    const feeds: Record<string, ort.Tensor> = {
      [inputName]: new ort.Tensor('float32', vec, [1, CANONICAL_SYMPTOMS.length]),
    };

    const results = await session!.run(feeds);

    // Find probability output: prefer names containing "prob", else last output
    const probName =
      session!.outputNames.find((n) => n.toLowerCase().includes('prob')) ??
      session!.outputNames[session!.outputNames.length - 1];

    const raw = results[probName].data as Float32Array;
    const probs = Array.from(raw);

    const indexed = probs.map((p, i) => ({ i, p }));
    indexed.sort((a, b) => b.p - a.p);
    const top3    = indexed.slice(0, 3);
    const primary = top3[0];

    return {
      primary_diagnosis: diseaseLabels[primary.i] ?? 'Unknown',
      confidence:        Math.round(primary.p * 1000) / 1000,
      differential:      top3.slice(1).map(({ i, p }) => ({
        disease:    diseaseLabels[i] ?? 'Unknown',
        confidence: Math.round(p * 1000) / 1000,
      })),
      source: 'tflite_offline' as const,
    };
  } catch (err) {
    console.warn('[Vaidya] Offline inference error:', err);
    return null;
  }
}

export function disposeOfflineModel(): void {
  session       = null;
  loadAttempted = false;
}
