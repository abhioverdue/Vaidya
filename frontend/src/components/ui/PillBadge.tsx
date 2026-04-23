import { View, Text, StyleSheet } from 'react-native';
import { COLORS, RADIUS } from '@/constants';

interface Props {
  label: string;
  color?: string;
  bg?: string;
  size?: 'sm' | 'md';
}

export function PillBadge({ label, color = COLORS.primary, bg = COLORS.primaryGhost, size = 'md' }: Props) {
  return (
    <View style={[styles.pill, { backgroundColor: bg }, size === 'sm' && styles.sm]}>
      <Text style={[styles.text, { color }, size === 'sm' && styles.textSm]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { borderRadius: RADIUS.pill, paddingHorizontal: 10, paddingVertical: 4, alignSelf: 'flex-start' },
  sm:   { paddingHorizontal: 7, paddingVertical: 2 },
  text: { fontSize: 12, fontWeight: '600' },
  textSm: { fontSize: 10 },
});
