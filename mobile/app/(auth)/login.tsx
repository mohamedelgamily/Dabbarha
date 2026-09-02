import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { Link } from 'expo-router';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, LoginFormData } from '@/schemas/auth';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Card } from '@/components/common/Card';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Logo } from '@/components/common/Logo';
import { colors, spacing } from '@/constants/theme';

export default function LoginScreen() {
  const { login, isLoading, error, clearError } = useAuthStore();

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
  });

  useEffect(() => {
    clearError();
  }, [clearError]);

  const onSubmit = async (data: LoginFormData) => {
    try {
      await login({
        email: data.email.trim().toLowerCase(),
        password: data.password,
      });
      // Navigation is automatically handled by route protection in app/_layout.tsx
    } catch {
      // Error message is captured in Zustand authStore.error
    }
  };

  return (
    <ScreenWrapper scrollable>
      <View style={styles.brandRow}>
        <Logo variant="full" tone="dark" />
      </View>
      <Typography
        variant="body"
        color={colors.textSecondary}
        align="center"
        style={styles.subtitle}
      >
        Financial Planning & Installment Tracking
      </Typography>

      <Card style={styles.formCard}>
        <Typography variant="h2" style={styles.formTitle}>
          Sign In
        </Typography>

        <ErrorBanner message={error} onDismiss={clearError} />

        <Controller
          control={control}
          name="email"
          render={({ field: { onChange, onBlur, value } }) => (
            <Input
              label="Email Address"
              placeholder="user@example.com"
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              value={value}
              onChangeText={(text) => {
                if (error) clearError();
                onChange(text);
              }}
              onBlur={onBlur}
              error={errors.email?.message}
            />
          )}
        />

        <Controller
          control={control}
          name="password"
          render={({ field: { onChange, onBlur, value } }) => (
            <Input
              label="Password"
              placeholder="••••••••"
              isPassword
              value={value}
              onChangeText={(text) => {
                if (error) clearError();
                onChange(text);
              }}
              onBlur={onBlur}
              error={errors.password?.message}
            />
          )}
        />

        <Button
          title="Sign In"
          onPress={handleSubmit(onSubmit)}
          isLoading={isLoading}
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
  brandRow: {
    marginTop: spacing.xl,
    marginBottom: spacing.xs,
    alignItems: 'center',
  },
  subtitle: {
    marginBottom: spacing.lg,
  },
  formCard: {
    marginTop: spacing.xs,
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
