import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { useAuthStore } from '@/store/authStore';
import { colors, spacing } from '@/constants/theme';

export default function ProfilePlaceholderScreen() {
  const { user, logout, isLoading } = useAuthStore();

  return (
    <ScreenWrapper scrollable>
      <View style={styles.header}>
        <Typography variant="h1">
          Profile
        </Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
          Account details and settings
        </Typography>
      </View>

      <Card style={styles.card}>
        <Typography variant="h3">
          {user?.name || 'Account User'}
        </Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.email}>
          {user?.email || 'user@example.com'}
        </Typography>
        <Typography variant="caption" color={colors.textMuted} style={styles.currency}>
          Currency: {user?.currency || 'EGP'}
        </Typography>
      </Card>

      <Button
        title="Sign Out"
        variant="danger"
        isLoading={isLoading}
        onPress={() => logout()}
        style={styles.logoutButton}
      />
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
  email: {
    marginTop: spacing.xs,
  },
  currency: {
    marginTop: spacing.xs,
  },
  logoutButton: {
    marginTop: spacing.xl,
  },
});
