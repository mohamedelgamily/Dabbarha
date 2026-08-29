import React from 'react';
import { View, StyleSheet, TouchableOpacity, StyleProp, ViewStyle } from 'react-native';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { Typography } from './Typography';

interface ErrorBannerProps {
  message: string | null;
  onDismiss?: () => void;
  style?: StyleProp<ViewStyle>;
}

export function ErrorBanner({ message, onDismiss, style }: ErrorBannerProps) {
  if (!message) return null;

  return (
    <View style={[styles.container, style]}>
      <View style={styles.content}>
        <Typography variant="bodyBold" color={colors.error} style={styles.icon}>
          ⚠️
        </Typography>
        <Typography variant="error" color={colors.error} style={styles.text}>
          {message}
        </Typography>
      </View>
      {onDismiss ? (
        <TouchableOpacity
          onPress={onDismiss}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          style={styles.dismissButton}
        >
          <Typography variant="caption" color={colors.error} style={styles.dismissText}>
            ✕
          </Typography>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.errorLight,
    borderColor: colors.error,
    borderWidth: 1,
    borderRadius: borderRadius.md,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  content: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  icon: {
    marginRight: spacing.sm,
    fontSize: 14,
  },
  text: {
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
  },
  dismissButton: {
    marginLeft: spacing.sm,
    padding: spacing.xs,
  },
  dismissText: {
    fontWeight: '700',
    fontSize: 14,
  },
});
