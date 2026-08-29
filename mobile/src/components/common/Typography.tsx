import React from 'react';
import { Text, TextStyle, StyleSheet, TextProps, StyleProp } from 'react-native';
import { colors, typography } from '@/constants/theme';

export type TypographyVariant =
  | 'hero'
  | 'h1'
  | 'h2'
  | 'h3'
  | 'body'
  | 'bodyBold'
  | 'caption'
  | 'label'
  | 'error';

interface TypographyProps extends TextProps {
  variant?: TypographyVariant;
  color?: string;
  align?: 'auto' | 'left' | 'right' | 'center' | 'justify';
  style?: StyleProp<TextStyle>;
  children: React.ReactNode;
}

export function Typography({
  variant = 'body',
  color,
  align = 'left',
  style,
  children,
  ...props
}: TypographyProps) {
  const variantStyle = variantStyles[variant];
  const textColor = color || defaultColors[variant];

  return (
    <Text
      style={[
        variantStyle,
        { color: textColor, textAlign: align },
        style,
      ]}
      {...props}
    >
      {children}
    </Text>
  );
}

const defaultColors: Record<TypographyVariant, string> = {
  hero: colors.textPrimary,
  h1: colors.textPrimary,
  h2: colors.textPrimary,
  h3: colors.textPrimary,
  body: colors.textPrimary,
  bodyBold: colors.textPrimary,
  caption: colors.textSecondary,
  label: colors.textSecondary,
  error: colors.error,
};

const variantStyles = StyleSheet.create({
  hero: {
    fontSize: typography.sizes.hero,
    fontWeight: typography.weights.bold,
    lineHeight: typography.lineHeights.hero,
  },
  h1: {
    fontSize: typography.sizes.xxl,
    fontWeight: typography.weights.bold,
    lineHeight: typography.lineHeights.xxl,
  },
  h2: {
    fontSize: typography.sizes.xl,
    fontWeight: typography.weights.semibold,
    lineHeight: typography.lineHeights.xl,
  },
  h3: {
    fontSize: typography.sizes.lg,
    fontWeight: typography.weights.semibold,
    lineHeight: typography.lineHeights.lg,
  },
  body: {
    fontSize: typography.sizes.md,
    fontWeight: typography.weights.regular,
    lineHeight: typography.lineHeights.md,
  },
  bodyBold: {
    fontSize: typography.sizes.md,
    fontWeight: typography.weights.semibold,
    lineHeight: typography.lineHeights.md,
  },
  caption: {
    fontSize: typography.sizes.xs,
    fontWeight: typography.weights.regular,
    lineHeight: typography.lineHeights.xs,
  },
  label: {
    fontSize: typography.sizes.sm,
    fontWeight: typography.weights.medium,
    lineHeight: typography.lineHeights.sm,
  },
  error: {
    fontSize: typography.sizes.xs,
    fontWeight: typography.weights.medium,
    lineHeight: typography.lineHeights.xs,
  },
});
