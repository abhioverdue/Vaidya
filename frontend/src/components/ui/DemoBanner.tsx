import { View, Text, StyleSheet } from 'react-native';
import { COLORS, TYPE, RADIUS } from '@/constants';

export function DemoBanner() {
  return (
    <View style={s.wrap}>
      <View style={s.dot} />
      <Text style={s.text}>Demo mode · Backend unreachable · Showing sample results</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 14,
    paddingVertical: 10,
    paddingHorizontal: 14,
    backgroundColor: '#FEF8EC',
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: 'rgba(154,107,31,0.2)',
  },
  dot:  { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.gold },
  text: { ...TYPE.bodySmall, color: COLORS.gold, fontWeight: '500', flex: 1 },
});
