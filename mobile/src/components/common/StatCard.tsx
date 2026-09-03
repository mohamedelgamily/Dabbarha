import React from 'react';
import { View, StyleSheet, StyleProp, ViewStyle, ViewProps } from 'react-native';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { Typography } from './Typography';
import { Icon, IconName, IconTone } from './Icon';

export type StatCardTone = 'default' | 'muted' | 'warning' | 'danger' | 'success' | 'inverse';

interface StatCardProps extends ViewProps {
  label: string;
  value: string;
  icon?: IconName;
  iconTone?: IconTone;
  hint?: string;
  tone?: StatCardTone;
  style?: StyleProp<ViewStyle>;
}

const TONE_BG: Record<StatCardTone, string> = {
  default: colors.surface,
  muted: colors.surfaceAlt,
  warning: colors.warningLight,
  danger: colors.errorLight,
  success: colors.successLight,
  inverse: colors.primary,
};

const TONE_LABEL: Record<StatCardTone, string> = {
  default: colors.textSecondary,
  muted: colors.textSecondary,
  warning: colors.warning,
  danger: colors.error,
  success: colors.success,
  inverse: 'rgba(255,255,255,0.72)',
};

const TONE_VALUE: Record<StatCardTone, string> = {
  default: colors.textPrimary,
  muted: colors.textPrimary,
  warning: colors.textPrimary,
  danger: colors.textPrimary,
  success: colors.textPrimary,
  inverse: colors.textInverse,
};

const TONE_ICON_BG: Record<StatCardTone, string> = {
  default: colors.primaryMuted,
  muted: colors.surface,
  warning: colors.surface,
  danger: colors.surface,
  success: colors.surface,
  inverse: 'rgba(255,255,255,0.12)',
};

const TONE_BORDER: Record<StatCardTone, string> = {
  default: colors.border,
  muted: 'transparent',
  warning: colors.warning,
  danger: colors.error,
  success: colors.success,
  inverse: 'transparent',
};

export function StatCard({
  label,
  value,
  icon,
  iconTone,
  hint,
  tone = 'default',
  style,
  ...props
}: StatCardProps) {
  const isInverse = tone === 'inverse';
  const resolvedIconTone: IconTone =
    iconTone ??
    (tone === 'inverse'
      ? 'inverse'
      : tone === 'warning'
        ? 'warning'
        : tone === 'danger'
          ? 'error'
          : tone === 'success'
            ? 'success'
            : 'primary');

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: TONE_BG[tone],
          borderColor: TONE_BORDER[tone],
        },
        style,
      ]}
      {...props}
    >
      <View style={styles.headerRow}>
        {icon ? (
          <View
            style={[
              styles.iconWrap,
              { backgroundColor: TONE_ICON_BG[tone] },
            ]}
          >
            <Icon name={icon} size={20} tone={resolvedIconTone} />
          </View>
        ) : null}
        <Typography
          variant="label"
          style={[styles.label, { color: TONE_LABEL[tone] }]}
          numberOfLines={1}
        >
          {label}
        </Typography>
      </View>

      <Typography
        variant="h2"
        style={[styles.value, { color: TONE_VALUE[tone] }]}
        numberOfLines={1}
      >
        {value}
      </Typography>

      {hint ? (
        <Typography
          variant="caption"
          style={[
            styles.hint,
            { color: isInverse ? 'rgba(255,255,255,0.72)' : colors.textMuted },
          ]}
          numberOfLines={2}
        >
          {hint}
        </Typography>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: borderRadius.xl,
    padding: spacing.md + 2,
    borderWidth: 1,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  iconWrap: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  label: {
    flexShrink: 1,
  },
  value: {
    fontSize: 24,
    lineHeight: 30,
  },
  hint: {
    marginTop: spacing.xs,
  },
});
