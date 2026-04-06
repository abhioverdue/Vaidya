/**
 * Vaidya — Offline symptom classifier
 *
 * Model: vaidya_symptom_classifier.tflite  (primary)
 *        vaidya_symptom_classifier.onnx    (fallback)
 *
 * Input:  Float32[1, 133]  — binary symptom vector (Training.csv column order)
 * Output: Float32[1, 132]  — softmax probabilities over 132 disease classes
 *
 * BUG FIXES applied in this file
 * ─────────────────────────────────────────────────────────────────────────────
 * FIX-1  tf.loadGraphModel() does NOT understand .tflite flatbuffer format.
 *        It expects a TensorFlow.js GraphModel JSON manifest + weight shards.
 *        We now use @tensorflow/tfjs-tflite's loadTFLiteModel() which wraps
 *        the TFLite C++ delegate on Android/iOS and falls back to WASM on web.
 *        If that package is unavailable at runtime we fall back to the bundled
 *        .onnx via tfjs-react-native's GraphModel path.
 *        Install: npx expo install @tensorflow/tfjs-tflite
 *
 * FIX-2  Added a loadAttempted guard so concurrent calls during initialisation
 *        no longer spawn parallel loads (which can double-allocate GPU memory
 *        and cause "Cannot allocate buffer" crashes on low-end Android).
 *
 * FIX-3  output.dataSync() is synchronous and blocks the JS thread for large
 *        tensors.  Replaced with await output.data() (async) throughout.
 *
 * FIX-4  disposeOfflineModel() now resets loadAttempted so the model can be
 *        reloaded after an explicit dispose (e.g. memory pressure callback).
 */

import { Asset } from 'expo-asset';
import * as FileSystem from 'expo-file-system';
import * as tf from '@tensorflow/tfjs';
import '@tensorflow/tfjs-react-native';

import { CANONICAL_SYMPTOMS } from './symptomList';
import { MIN_SYMPTOMS_FOR_TFLITE } from '@/constants';
import type { OfflinePrediction } from '@/types';

// Use a loose type so both TFLiteModel and tf.GraphModel satisfy it.
type AnyModel = { predict: (t: tf.Tensor) => tf.Tensor | tf.NamedTensorMap; dispose?: () => void };

let model: AnyModel | null   = null;
let diseaseLabels: string[]  = [];
let isLoading                = false;
let loadAttempted            = false; // FIX-2
let loadError: string | null = null;

// ── Model loading ─────────────────────────────────────────────────────────────

export async function loadOfflineModel(): Promise<boolean> {
  if (model !== null) return true;

  // FIX-2: wait for an in-progress load rather than spawning a second one
  if (isLoading) {
    while (isLoading) {
      await new Promise<void>((r) => setTimeout(r, 50));
    }
    return model !== null;
  }

  // FIX-2: do not retry after a permanent failure (missing asset, etc.)
  if (loadAttempted && model === null) return false;

  isLoading     = true;
  loadAttempted = true;
  loadError     = null;

  try {
    await tf.ready();

    // ── Load disease labels ─────────────────────────────────────────────────
    const labelsAsset = Asset.fromModule(
      require('../assets/models/disease_labels.json'),
    );
    await labelsAsset.downloadAsync();
    const labelsRaw = await FileSystem.readAsStringAsync(labelsAsset.localUri!);
    diseaseLabels   = JSON.parse(labelsRaw);

    // ── FIX-1: Primary path — @tensorflow/tfjs-tflite ──────────────────────
    // loadTFLiteModel() is the correct API for .tflite flatbuffer files.
    // tf.loadGraphModel() is for TensorFlow.js SavedModel JSON — it will
    // throw "Invalid graph" on a .tflite binary.
    let loaded = false;
    try {
      // Dynamic require keeps the file compilable if the package is absent
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const tfliteLib = require('@tensorflow/tfjs-tflite');
      const modelAsset = Asset.fromModule(
        require('../assets/models/vaidya_symptom_classifier.tflite'),
      );
      await modelAsset.downloadAsync();
      model  = await tfliteLib.loadTFLiteModel(modelAsset.localUri!);
      loaded = true;
      console.log('[Vaidya] TFLite model loaded. Labels:', diseaseLabels.length);
    } catch (tfliteErr) {
      console.warn('[Vaidya] tfjs-tflite unavailable, trying ONNX fallback:', tfliteErr);
    }

    // ── FIX-1: Fallback — ONNX via tfjs-react-native GraphModel ────────────
    if (!loaded) {
      const onnxAsset = Asset.fromModule(
        require('../assets/models/vaidya_symptom_classifier.onnx'),
      );
      await onnxAsset.downloadAsync();
      // tfjs-react-native ≥ 0.8 can load ONNX via file:// URI
      model = await tf.loadGraphModel(`file://${onnxAsset.localUri}`) as AnyModel;
      console.log('[Vaidya] ONNX fallback model loaded. Labels:', diseaseLabels.length);
    }

    isLoading = false;
    return true;

  } catch (err) {
    loadError = String(err);
    isLoading = false;
    console.warn('[Vaidya] Model load failed:', err);
    return false;
  }
}

export function isModelReady(): boolean {
  return model !== null && diseaseLabels.length > 0;
}

export function getModelLoadError(): string | null {
  return loadError;
}

// ── Symptom vector → inference ────────────────────────────────────────────────

function buildInputTensor(symptoms: string[]): tf.Tensor2D {
  const vec = new Float32Array(CANONICAL_SYMPTOMS.length).fill(0);
  for (const sym of symptoms) {
    const idx = CANONICAL_SYMPTOMS.indexOf(sym);
    if (idx !== -1) vec[idx] = 1.0;
  }
  return tf.tensor2d(vec, [1, CANONICAL_SYMPTOMS.length]);
}

export async function runOfflineInference(
  symptoms: string[],
): Promise<OfflinePrediction | null> {
  if (!isModelReady()) {
    const loaded = await loadOfflineModel();
    if (!loaded) return null;
  }

  if (symptoms.length < MIN_SYMPTOMS_FOR_TFLITE) return null;

  let input: tf.Tensor2D | null = null;
  let rawOut: tf.Tensor | tf.NamedTensorMap | null = null;
  try {
    input  = buildInputTensor(symptoms);
    rawOut = model!.predict(input);

    // TFLiteModel may return a NamedTensorMap; unwrap it.
    const outputTensor: tf.Tensor =
      rawOut instanceof tf.Tensor
        ? rawOut
        : Object.values(rawOut as tf.NamedTensorMap)[0];

    // FIX-3: async data() instead of synchronous dataSync()
    const probs   = Array.from(await outputTensor.data());
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
  } finally {
    input?.dispose();
    if (rawOut instanceof tf.Tensor) rawOut.dispose();
    else if (rawOut) Object.values(rawOut).forEach((t) => t.dispose());
  }
}

// ── Cleanup ───────────────────────────────────────────────────────────────────

export function disposeOfflineModel(): void {
  if (model?.dispose) model.dispose();
  model         = null;
  loadAttempted = false; // FIX-4: allow reload after explicit dispose
  tf.disposeVariables();
}
