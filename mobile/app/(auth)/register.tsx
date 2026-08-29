import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Link } from 'expo-router';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Card } from '@/components/common/Card';
import { colors, spacing } from '@/constants/theme';

export default function RegisterPlaceholderScreen() {
  return (
    <ScreenWrapper scrollable>
      <View style={styles.header}>
        <Typography variant="hero" color={colors.primary} align="center">
          دبّرها | Dabbarha
        </Typography>
        <Typography variant="body" color={colors.textSecondary} align="center" style={styles.subtitle}>
          Create your account
        </Typography>
      </View>

      <Card style={styles.formCard}>
        <Typography variant="h2" style={styles.formTitle}>
          Register
        </Typography>

        <Input
          label="Full Name"
          placeholder="Ahmed Mohamed"
          editable={false}
        />

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
          title="Register (Placeholder)"
          disabled
          style={styles.button}
        />

        <View style={styles.footerRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Already have an account?{' '}
          </Typography>
          <Link href="/(auth)/login" asChild>
            <Typography variant="caption" color={colors.primary} style={styles.link}>
              Sign In
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
