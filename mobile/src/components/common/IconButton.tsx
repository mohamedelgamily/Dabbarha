import React from 'react';
import {
  TouchableOpacity,
  StyleSheet,
  StyleProp,
  ViewStyle,
  TouchableOpacityProps,
  ActivityIndicator,
} from 'react-native';
import { colors } from '@/constants/theme';
import { Icon, IconName } from './Icon';

interface IconButtonProps extends Omit<TouchableOpacityProps, 'children' | 'style'> {
  name: IconName;
  size?: number;
  iconSize?: number;
  variant?: 'plain' | 'filled' | 'soft';
  tone?: 'primary' | 'secondary' | 'muted' | 'inverse';
  isLoading?: boolean;
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}

export function IconButton({
  name,
  size = 40,
  iconSize,
  variant = 'plain',
  tone = 'primary',
  isLoading = false,
  disabled,
  style,
  accessibilityLabel,
  ...props
}: IconButtonProps) {
  const isDisabled = disabled || isLoading;
  const resolvedIconSize = iconSize ?? Math.round(size * 0.5);

  const variantStyle =
    variant === 'filled'
      ? styles.filled
      : variant === 'soft'
        ? styles.soft
        : styles.plain;
  const toneColor =
    tone === 'inverse'
      ? colors.textInverse
      : tone === 'secondary'
        ? colors.secondary
        : tone === 'muted'
          ? colors.textMuted
          : colors.primary;

  return (
    <TouchableOpacity
      activeOpacity={0.7}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? name}
      style={[
        styles.base,
        { width: size, height: size, borderRadius: size / 2 },
        variantStyle,
        isDisabled && styles.disabled,
        style,
      ]}
      {...props}
    >
      {isLoading ? (
        <ActivityIndicator size="small" color={toneColor} />
      ) : (
        <Icon
          name={name}
          size={resolvedIconSize}
          color={toneColor}
        />
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  plain: {
    backgroundColor: 'transparent',
  },
  filled: {
    backgroundColor: colors.primary,
  },
  soft: {
    backgroundColor: colors.surfaceAlt,
  },
  disabled: {
    opacity: 0.5,
  },
});
