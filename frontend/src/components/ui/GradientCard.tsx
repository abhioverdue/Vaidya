/**
 * GradientCard — shared elevated card surface used throughout Vaidya.
 * Variants: default | elevated | ghost
 */
import { View, StyleSheet, ViewStyle } from 'react-native';
import { COLORS, RADIUS } from '@/constants';

interface Props {
  children: React.ReactNode;
  style?: ViewStyle;
  variant?: 'default' | 'elevated' | 'ghost';
  /** Override background — useful for tinted alert cards */
  tint?: string;
  noPad?: boolean;
}

export function GradientCard({
  children,
  style,
  variant = 'default',
  tint,
  noPad,
}: Props) {
  const bg =
    tint      ? tint
    : variant === 'ghost' ? COLORS.inkGhost
    : COLORS.surface;

  return (
    <View
      style={[
        styles.base,
        variant === 'elevated' && styles.elevated,
        variant === 'ghost'    && styles.ghost,
        { backgroundColor: bg },
        noPad && { padding: 0 },
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: 10,
  },
  elevated: {
    shadowColor: COLORS.ink,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
    borderColor: 'transparent',
  },
  ghost: {
    borderColor: COLORS.border,
    backgroundColor: COLORS.inkGhost,
  },
});
