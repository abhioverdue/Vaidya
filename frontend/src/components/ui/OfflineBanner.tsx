import { View, Text, StyleSheet } from 'react-native';
import { COLORS, TYPE, RADIUS } from '@/constants';

export function OfflineBanner() {
  return (
    <View style={s.wrap}>
      <View style={s.dot} />
      <Text style={s.text}>Offline · On-device model active</Text>
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
    backgroundColor: COLORS.parchmentWarm,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  dot:  { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.textFaint },
  text: { ...TYPE.bodySmall, color: COLORS.textMuted, fontWeight: '500' },
});
