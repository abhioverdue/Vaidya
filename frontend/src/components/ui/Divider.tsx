import { View } from 'react-native';
import { COLORS } from '@/constants';

export function Divider({ my = 12 }: { my?: number }) {
  return <View style={{ height: 1, backgroundColor: COLORS.border, marginVertical: my }} />;
}
