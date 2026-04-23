/**
 * IconButton — circular icon-only button for header actions.
 * Takes a React node as its icon (or a text glyph for arrow/close).
 */
import { TouchableOpacity, View, StyleSheet } from 'react-native';
import * as Haptics from 'expo-haptics';
import { COLORS, RADIUS } from '@/constants';

interface Props {
  onPress: () => void;
  icon: React.ReactNode;
  size?: number;
  variant?: 'default' | 'filled' | 'ghost';
  accessibilityLabel?: string;
}

export function IconButton({
  onPress, icon, size = 36,
  variant = 'default',
  accessibilityLabel,
}: Props) {
  async function handlePress() {
    await Haptics.selectionAsync();
    onPress();
  }

  return (
    <TouchableOpacity
      onPress={handlePress}
      activeOpacity={0.7}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={[
        styles.btn,
        { width: size, height: size, borderRadius: size / 2 },
        variant === 'filled' && styles.filled,
        variant === 'ghost'  && styles.ghost,
      ]}
    >
      <View style={styles.inner}>
        {icon}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  btn: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.inkGhost,
  },
  filled: {
    backgroundColor: COLORS.ink,
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  inner: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
