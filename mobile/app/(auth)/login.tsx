import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Link } from 'expo-router';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Card } from '@/components/common/Card';
import { colors, spacing } from '@/constants/theme';

export default function LoginPlaceholderScreen() {
  return (
    <ScreenWrapper scrollable>
      <View style={styles.header}>
        <Typography variant="hero" color={colors.primary} align="center">
          دبّرها | Dabbarha
        </Typography>
        <Typography variant="body" color={colors.textSecondary} align="center" style={styles.subtitle}>
          Financial Planning & Installment Tracking
        </Typography>
      </View>

      <Card style={styles.formCard}>
        <Typography variant="h2" style={styles.formTitle}>
          Sign In
        </Typography>

        <Input
          label="Email Address"
          placeholder="user@example.com"
          keyboardType="email-address"
          autoCapitalize="none"
          editable={false}
        />

        <Input
          label="Password"
          placeholder="••••••••"
          isPassword
          editable={false}
        />

        <Button
          title="Sign In (Placeholder)"
          disabled
          style={styles.button}
        />

        <View style={styles.footerRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Don't have an account?{' '}
          </Typography>
          <Link href="/(auth)/register" asChild>
            <Typography variant="caption" color={colors.primary} style={styles.link}>
              Create Account
            </Typography>
          </Link>
        </View>
      </Card>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  header: {
    marginVertical: spacing.xl,
  },
  subtitle: {
    marginTop: spacing.xs,
  },
  formCard: {
    marginTop: spacing.md,
  },
  formTitle: {
    marginBottom: spacing.lg,
  },
  button: {
    marginTop: spacing.sm,
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: spacing.lg,
  },
  link: {
    fontWeight: '600',
  },
});
