/**
 * Web stub — ONNX Runtime React Native is native-only.
 * Offline inference is not available on web; the app always uses the backend there.
 */

import type { OfflinePrediction } from '@/types';

export async function loadOfflineModel(): Promise<boolean> { return false; }
export function isModelReady(): boolean { return false; }
export function getModelLoadError(): string | null { return null; }
export async function runOfflineInference(_s: string[]): Promise<OfflinePrediction | null> { return null; }
export function disposeOfflineModel(): void {}
