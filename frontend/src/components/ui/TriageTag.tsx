/**
 * TriageTag — compact triage-level badge used in session history rows and cards.
 */
import { View, Text, StyleSheet } from 'react-native';
import { COLORS, RADIUS, TRIAGE_CONFIG, TYPE } from '@/constants';
import type { TriageLevel } from '@/types';

interface Props {
  level: TriageLevel;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function TriageTag({ level, showLabel = true, size = 'md' }: Props) {
  const cfg = TRIAGE_CONFIG[level];

  const containerStyle = [
    styles.base,
    size === 'sm' && styles.sm,
    size === 'lg' && styles.lg,
    { backgroundColor: cfg.bgColor, borderColor: cfg.borderColor },
  ];

  return (
    <View style={containerStyle}>
      <View style={[styles.dot, { backgroundColor: cfg.color }]} />
      {showLabel && (
        <Text style={[
          styles.label,
          { color: cfg.color },
          size === 'sm' && styles.labelSm,
          size === 'lg' && styles.labelLg,
        ]}>
          {cfg.label}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  sm:      { paddingHorizontal: 6, paddingVertical: 2 },
  lg:      { paddingHorizontal: 12, paddingVertical: 6 },
  dot:     { width: 5, height: 5, borderRadius: 3 },
  label:   { ...TYPE.micro, fontWeight: '700', letterSpacing: 0.4 },
  labelSm: { fontSize: 9 },
  labelLg: { fontSize: 12, letterSpacing: 0.2 },
});
