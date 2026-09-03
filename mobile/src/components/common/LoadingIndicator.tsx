import React from 'react';
import { View, StyleSheet, ViewStyle, StyleProp, ActivityIndicator } from 'react-native';
import { colors, spacing } from '@/constants/theme';
import { Typography } from './Typography';

interface LoadingIndicatorProps {
  message?: string;
  size?: 'small' | 'large';
  color?: string;
  style?: StyleProp<ViewStyle>;
}

export function LoadingIndicator({
  message,
  size = 'large',
  color = colors.primary,
  style,
}: LoadingIndicatorProps) {
  return (
    <View style={[styles.container, style]}>
      <ActivityIndicator size={size} color={color} />
      {message ? (
        <Typography variant="body" color={colors.textSecondary} style={styles.message}>
          {message}
        </Typography>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  message: {
    marginTop: spacing.md,
    textAlign: 'center',
  },
});
