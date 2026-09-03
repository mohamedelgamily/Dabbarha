import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { Link, router } from 'expo-router';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { registerSchema, RegisterFormData } from '@/schemas/auth';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Card } from '@/components/common/Card';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Logo } from '@/components/common/Logo';
import { colors, spacing } from '@/constants/theme';

export default function RegisterScreen() {
  const { register, isLoading, error, clearError } = useAuthStore();

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      name: '',
      email: '',
      password: '',
      monthly_income: '',
      fixed_expenses: '',
      currency: 'EGP',
    },
  });

  useEffect(() => {
    clearError();
  }, [clearError]);

  const onSubmit = async (data: RegisterFormData) => {
    try {
      const monthlyIncome =
        data.monthly_income && data.monthly_income.trim() !== ''
          ? Number(data.monthly_income)
          : 0;
      const fixedExpenses =
        data.fixed_expenses && data.fixed_expenses.trim() !== ''
          ? Number(data.fixed_expenses)
          : 0;

      await register({
        name: data.name.trim(),
        email: data.email.trim().toLowerCase(),
        password: data.password,
        monthly_income: monthlyIncome,
        fixed_expenses: fixedExpenses,
        currency: (data.currency || 'EGP').trim().toUpperCase(),
      });

      router.replace('/(auth)/login');
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
        Create your financial account
      </Typography>

      <Card style={styles.formCard}>
        <Typography variant="h2" style={styles.formTitle}>
          Create Account
        </Typography>

        <ErrorBanner message={error} onDismiss={clearError} />

        <Controller
          control={control}
          name="name"
          render={({ field: { onChange, onBlur, value } }) => (
            <Input
              label="Full Name *"
              placeholder="e.g. Ahmed Mohamed"
              value={value}
              onChangeText={(text) => {
                if (error) clearError();
                onChange(text);
              }}
              onBlur={onBlur}
              error={errors.name?.message}
            />
          )}
        />

        <Controller
          control={control}
          name="email"
          render={({ field: { onChange, onBlur, value } }) => (
            <Input
              label="Email Address *"
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
              label="Password *"
              placeholder="At least 6 characters"
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

        <View style={styles.row}>
          <View style={styles.halfCol}>
            <Controller
              control={control}
              name="monthly_income"
              render={({ field: { onChange, onBlur, value } }) => (
                <Input
                  label="Monthly Income"
                  placeholder="0.00"
                  keyboardType="decimal-pad"
                  value={value}
                  onChangeText={(text) => {
                    if (error) clearError();
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.monthly_income?.message}
                  helperText="Optional"
                />
              )}
            />
          </View>
          <View style={styles.halfCol}>
            <Controller
              control={control}
              name="fixed_expenses"
              render={({ field: { onChange, onBlur, value } }) => (
                <Input
                  label="Fixed Expenses"
                  placeholder="0.00"
                  keyboardType="decimal-pad"
                  value={value}
                  onChangeText={(text) => {
                    if (error) clearError();
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.fixed_expenses?.message}
                  helperText="Optional"
                />
              )}
            />
          </View>
        </View>

        <Controller
          control={control}
          name="currency"
          render={({ field: { onChange, onBlur, value } }) => (
            <Input
              label="Currency Code"
              placeholder="EGP"
              autoCapitalize="characters"
              maxLength={3}
              value={value}
              onChangeText={(text) => {
                if (error) clearError();
                onChange(text);
              }}
              onBlur={onBlur}
              error={errors.currency?.message}
              helperText="Default: EGP"
            />
          )}
        />

        <Button
          title="Create Account"
          onPress={handleSubmit(onSubmit)}
          isLoading={isLoading}
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
  row: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  halfCol: {
    flex: 1,
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
