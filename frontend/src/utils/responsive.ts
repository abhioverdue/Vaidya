import { Dimensions } from 'react-native';
export { useWindowDimensions } from 'react-native';

const BASE_WIDTH  = 390;  // iPhone 14 / Pixel 7 — common design reference
const BASE_HEIGHT = 844;

const { width: W, height: H } = Dimensions.get('window');

/** Width-proportional scale — use for icons, buttons, horizontal spacing */
export const scale = (n: number): number => (W / BASE_WIDTH) * n;

/** Height-proportional scale — use for tall components, vertical spacing */
export const vScale = (n: number): number => (H / BASE_HEIGHT) * n;

/**
 * Moderate scale — blends 1:1 with width-scaled value.
 * factor=0 → no scaling, factor=1 → full width-proportional scaling.
 * Ideal for font sizes and things that should scale but not aggressively.
 */
export const mScale = (n: number, factor = 0.45): number =>
  n + (scale(n) - n) * factor;

export const SCREEN_W = W;
export const SCREEN_H = H;
