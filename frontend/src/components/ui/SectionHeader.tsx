/**
 * SectionHeader — consistent section title used across all Vaidya screens.
 * Supports an optional trailing badge count and an optional action label.
 */
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { COLORS, TYPE, RADIUS } from '@/constants';

interface Props {
  title: string;
  badge?: number | string;
  action?: { label: string; onPress: () => void };
}

export function SectionHeader({ title, badge, action }: Props) {
  return (
    <View style={styles.row}>
      <View style={styles.titleGroup}>
        <Text style={styles.title}>{title.toUpperCase()}</Text>
        {badge !== undefined && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{badge}</Text>
          </View>
        )}
      </View>

      {action && (
        <TouchableOpacity onPress={action.onPress} activeOpacity={0.7}>
          <Text style={styles.action}>{action.label}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row:        { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  titleGroup: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title:      { ...TYPE.label, color: COLORS.textMuted, letterSpacing: 1.5 },
  badge: {
    backgroundColor: COLORS.inkGhost,
    borderRadius: RADIUS.pill,
    paddingHorizontal: 6,
    paddingVertical: 1,
    minWidth: 20,
    alignItems: 'center',
  },
  badgeText:  { ...TYPE.micro, color: COLORS.textMuted, fontWeight: '700' },
  action:     { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '600' },
});
