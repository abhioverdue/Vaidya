/**
 * StatusIndicator — animated pill showing AI model / connectivity status
 * Shown in header bars throughout Vaidya.
 */
import { View, Text, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withRepeat, withSequence, withTiming,
} from 'react-native-reanimated';
import { useEffect } from 'react';
import { COLORS, RADIUS, TYPE } from '@/constants';

interface Props {
  online: boolean;
  label?: string;
}

export function StatusIndicator({ online, label }: Props) {
  const opacity = useSharedValue(1);

  useEffect(() => {
    if (online) {
      opacity.value = withRepeat(
        withSequence(
          withTiming(0.35, { duration: 800 }),
          withTiming(1,    { duration: 800 }),
        ),
        -1,
        false,
      );
    } else {
      opacity.value = 0.5;
    }
  }, [online]);

  const dotStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <View style={[styles.pill, online ? styles.pillOnline : styles.pillOffline]}>
      <Animated.View style={[
        styles.dot,
        { backgroundColor: online ? COLORS.sage : COLORS.textFaint },
        dotStyle,
      ]} />
      <Text style={[styles.label, { color: online ? COLORS.sage : COLORS.textMuted }]}>
        {label ?? (online ? 'AI · Online' : 'Offline model')}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
  },
  pillOnline:  { backgroundColor: COLORS.sageGhost,   borderColor: 'rgba(58,95,82,0.18)' },
  pillOffline: { backgroundColor: COLORS.inkGhost,     borderColor: COLORS.border },
  dot:   { width: 5, height: 5, borderRadius: 3 },
  label: { ...TYPE.micro, fontWeight: '600', letterSpacing: 0.3 },
});
