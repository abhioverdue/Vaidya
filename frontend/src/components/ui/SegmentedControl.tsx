/**
 * SegmentedControl — iOS-style segmented picker
 * Used in the Care screen for PHC / CHC / District / Private tabs.
 */
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withSpring,
} from 'react-native-reanimated';
import { useEffect, useRef, useState } from 'react';
import { COLORS, RADIUS, TYPE } from '@/constants';

interface Segment<T extends string> {
  key: T;
  label: string;
  badge?: number;
}

interface Props<T extends string> {
  segments: Segment<T>[];
  value: T;
  onChange: (key: T) => void;
  scrollable?: boolean;
}

export function SegmentedControl<T extends string>({
  segments, value, onChange, scrollable = false,
}: Props<T>) {
  const [containerWidth, setContainerWidth] = useState(0);
  const selectedIndex = segments.findIndex((s) => s.key === value);
  const segW = containerWidth / segments.length;

  const translateX = useSharedValue(0);

  useEffect(() => {
    if (containerWidth > 0) {
      translateX.value = withSpring(selectedIndex * segW, {
        damping: 18, stiffness: 260,
      });
    }
  }, [selectedIndex, segW, containerWidth]);

  const thumbStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }],
    width: segW - 4,
  }));

  const inner = (
    <View
      style={styles.track}
      onLayout={(e) => setContainerWidth(e.nativeEvent.layout.width)}
    >
      {/* Sliding thumb */}
      {containerWidth > 0 && (
        <Animated.View style={[styles.thumb, thumbStyle]} />
      )}

      {segments.map((seg) => {
        const active = seg.key === value;
        return (
          <TouchableOpacity
            key={seg.key}
            style={styles.segment}
            onPress={() => onChange(seg.key)}
            activeOpacity={0.7}
          >
            <Text style={[styles.segLabel, active && styles.segLabelActive]}>
              {seg.label}
            </Text>
            {seg.badge !== undefined && seg.badge > 0 && (
              <View style={[styles.badge, active && styles.badgeActive]}>
                <Text style={[styles.badgeText, active && styles.badgeTextActive]}>
                  {seg.badge > 99 ? '99+' : seg.badge}
                </Text>
              </View>
            )}
          </TouchableOpacity>
        );
      })}
    </View>
  );

  if (scrollable) {
    return (
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.scrollWrap}>
        {inner}
      </ScrollView>
    );
  }

  return inner;
}

const styles = StyleSheet.create({
  scrollWrap: { flexGrow: 0 },
  track: {
    flexDirection: 'row',
    backgroundColor: COLORS.inkGhost,
    borderRadius: RADIUS.lg,
    padding: 2,
    position: 'relative',
    overflow: 'hidden',
  },
  thumb: {
    position: 'absolute',
    top: 2,
    left: 2,
    bottom: 2,
    backgroundColor: COLORS.surface,
    borderRadius: RADIUS.md,
    shadowColor: COLORS.ink,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 2,
  },
  segment: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    gap: 4,
    zIndex: 1,
  },
  segLabel:       { ...TYPE.bodySmall, fontWeight: '500', color: COLORS.textMuted },
  segLabelActive: { color: COLORS.ink, fontWeight: '600' },
  badge: {
    backgroundColor: COLORS.border,
    borderRadius: 8,
    paddingHorizontal: 5,
    paddingVertical: 1,
    minWidth: 16,
    alignItems: 'center',
  },
  badgeActive:     { backgroundColor: COLORS.inkGhost },
  badgeText:       { fontSize: 9, fontWeight: '700', color: COLORS.textMuted },
  badgeTextActive: { color: COLORS.ink },
});
