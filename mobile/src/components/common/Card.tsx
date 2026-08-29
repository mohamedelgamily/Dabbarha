import React from 'react';
import { View, StyleSheet, ViewProps, ViewStyle, StyleProp } from 'react-native';
import { colors, spacing, borderRadius, shadows } from '@/constants/theme';

interface CardProps extends ViewProps {
  style?: StyleProp<ViewStyle>;
  children: React.ReactNode;
  variant?: 'elevated' | 'outlined' | 'flat';
}

export function Card({
  style,
  children,
  variant = 'elevated',
  ...props
}: CardProps) {
  return (
    <View
      style={[
        styles.base,
        variant === 'elevated' && styles.elevated,
        variant === 'outlined' && styles.outlined,
        variant === 'flat' && styles.flat,
        style,
      ]}
      {...props}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
  },
  elevated: {
    ...shadows.sm,
  },
  outlined: {
    borderWidth: 1,
    borderColor: colors.border,
  },
  flat: {
    backgroundColor: colors.surfaceAlt,
  },
});
