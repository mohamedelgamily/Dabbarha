import React from 'react';
import { View, StyleSheet, TouchableOpacity, StyleProp, ViewStyle } from 'react-native';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { Typography } from './Typography';
import { Icon } from './Icon';

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
        <View style={styles.iconWrap}>
          <Icon name="alert-triangle" size={18} tone="error" />
        </View>
        <Typography variant="error" color={colors.error} style={styles.text}>
          {message}
        </Typography>
      </View>
      {onDismiss ? (
        <TouchableOpacity
          onPress={onDismiss}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          style={styles.dismissButton}
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
        >
          <Icon name="x" size={16} tone="error" />
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
  iconWrap: {
    marginRight: spacing.sm,
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
});
