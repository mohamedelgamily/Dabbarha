import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Card } from '@/components/common/Card';
import { useAuthStore } from '@/store/authStore';
import { colors, spacing } from '@/constants/theme';

export default function DashboardPlaceholderScreen() {
  const { user } = useAuthStore();

  return (
    <ScreenWrapper scrollable>
      <View style={styles.header}>
        <Typography variant="h1">
          Welcome, {user?.name || 'User'} 👋
        </Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
          Dabbarha Financial Overview
        </Typography>
      </View>

      <Card style={styles.card}>
        <Typography variant="h3" color={colors.primary}>
          Foundation Ready
        </Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.cardText}>
          Mobile app foundation is initialized with React Native, Expo Router, TypeScript, Zustand, and TanStack Query.
        </Typography>
      </Card>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  header: {
    marginVertical: spacing.md,
  },
  subtitle: {
    marginTop: spacing.xs,
  },
  card: {
    marginTop: spacing.md,
  },
  cardText: {
    marginTop: spacing.sm,
    lineHeight: 22,
  },
});
