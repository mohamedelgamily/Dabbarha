import React from 'react';
import { Text, TextStyle, StyleSheet, TextProps, StyleProp } from 'react-native';
import { colors, typography } from '@/constants/theme';

export type TypographyVariant =
  | 'hero'
  | 'display'
  | 'h1'
  | 'h2'
  | 'h3'
  | 'body'
  | 'bodyMedium'
  | 'bodyBold'
  | 'caption'
  | 'label'
  | 'kicker'
  | 'mono'
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
  display: colors.textPrimary,
  h1: colors.textPrimary,
  h2: colors.textPrimary,
  h3: colors.textPrimary,
  body: colors.textPrimary,
  bodyMedium: colors.textPrimary,
  bodyBold: colors.textPrimary,
  caption: colors.textSecondary,
  label: colors.textSecondary,
  kicker: colors.textMuted,
  mono: colors.textPrimary,
  error: colors.error,
};

const variantStyles = StyleSheet.create({
  hero: {
    fontFamily: typography.fontFamily, ...typography.title,
    fontSize: typography.sizes.hero, lineHeight: typography.lineHeights.hero,
    fontVariant: ['tabular-nums'],
  },
  display: {
    fontFamily: typography.fontFamily, ...typography.title,
    fontSize: typography.sizes.display, lineHeight: typography.lineHeights.display,
    fontVariant: ['tabular-nums'],
  },
  h1: {
    fontFamily: typography.fontFamily, ...typography.title,
    fontSize: typography.sizes.xxl, lineHeight: typography.lineHeights.xxl,
  },
  h2: {
    fontFamily: typography.fontFamily, ...typography.title,
    fontSize: typography.sizes.xl, lineHeight: typography.lineHeights.xl,
  },
  h3: {
    fontFamily: typography.fontFamily, ...typography.title,
    fontSize: typography.sizes.lg, lineHeight: typography.lineHeights.lg,
  },
  body: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.md,
    fontWeight: typography.weights.regular,
    lineHeight: typography.lineHeights.md,
    letterSpacing: typography.letterSpacing.normal,
  },
  bodyMedium: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.md,
    fontWeight: typography.weights.medium,
    lineHeight: typography.lineHeights.md,
    letterSpacing: typography.letterSpacing.normal,
  },
  bodyBold: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.md,
    fontWeight: typography.weights.semibold,
    lineHeight: typography.lineHeights.md,
    letterSpacing: typography.letterSpacing.normal,
  },
  caption: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.xs,
    fontWeight: typography.weights.regular,
    lineHeight: typography.lineHeights.xs,
    letterSpacing: typography.letterSpacing.normal,
  },
  label: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.sm,
    fontWeight: typography.weights.semibold,
    lineHeight: typography.lineHeights.sm,
    letterSpacing: typography.letterSpacing.wide,
  },
  kicker: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.kicker,
    fontWeight: typography.weights.bold,
    lineHeight: typography.lineHeights.kicker,
    letterSpacing: typography.letterSpacing.kicker,
    textTransform: 'uppercase',
  },
  mono: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.md,
    fontWeight: typography.weights.semibold,
    lineHeight: typography.lineHeights.md,
    fontVariant: ['tabular-nums'],
    letterSpacing: typography.letterSpacing.tight,
  },
  error: {
    fontFamily: typography.fontFamily,
    fontSize: typography.sizes.xs,
    fontWeight: typography.weights.medium,
    lineHeight: typography.lineHeights.xs,
  },
});
