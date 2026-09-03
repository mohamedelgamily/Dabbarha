import React from 'react';
import { View, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { colors, spacing } from '@/constants/theme';
import { Typography } from './Typography';
import { Button } from './Button';
import { Icon, IconName } from './Icon';

interface EmptyStateProps {
  icon?: IconName;
  title: string;
  body?: string;
  actionLabel?: string;
  onAction?: () => void;
  style?: StyleProp<ViewStyle>;
}

export function EmptyState({
  icon = 'file-text',
  title,
  body,
  actionLabel,
  onAction,
  style,
}: EmptyStateProps) {
  return (
    <View style={[styles.container, style]}>
      <View style={styles.iconWrap}>
        <Icon name={icon} size={28} tone="primary" />
      </View>
      <Typography variant="h2" align="center" style={styles.title}>
        {title}
      </Typography>
      {body ? (
        <Typography
          variant="body"
          color={colors.textSecondary}
          align="center"
          style={styles.body}
        >
          {body}
        </Typography>
      ) : null}
      {actionLabel && onAction ? (
        <Button title={actionLabel} onPress={onAction} style={styles.action} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.lg,
  },
  iconWrap: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  title: {
    marginBottom: spacing.xs,
  },
  body: {
    lineHeight: 22,
    marginBottom: spacing.lg,
    maxWidth: 320,
  },
  action: {
    minWidth: 220,
  },
});
