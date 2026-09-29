import { t } from '@/i18n';
import React, { useEffect } from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Link } from 'expo-router';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, LoginFormData } from '@/schemas/auth';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Logo } from '@/components/common/Logo';
import { colors, spacing, borderRadius } from '@/constants/theme';

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
      // Route protection in app/_layout.tsx navigates to tabs
    } catch {
      // Captured in authStore.error
    }
  };

  return (
    <ScreenWrapper scrollable>
      {/* Brand Header */}
      <View style={styles.brandContainer}>
        <Logo variant="full" tone="dark" width={260} />
      </View>

      {/* Login Card */}
      <View style={styles.formCard}>
        <Typography style={styles.formHeading}>
          {t("Sign In")}</Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.formSub}>
          {t("Access your financial control center")}</Typography>

        <ErrorBanner message={error} onDismiss={clearError} />

        <Controller
          control={control}
          name="email"
          render={({ field: { onChange, onBlur, value } }) => (
            <Input
              label={t("Email Address")}
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
              label={t("Password")}
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
          title={t("Sign In")}
          onPress={handleSubmit(onSubmit)}
          isLoading={isLoading}
          style={styles.submitButton}
        />

        <View style={styles.footerRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            {t("Don't have an account?")}{' '}
          </Typography>
          <Link href="/(auth)/register" asChild>
            <TouchableOpacity activeOpacity={0.7}>
              <Typography style={styles.linkText}>
                {t("Create Account")}</Typography>
            </TouchableOpacity>
          </Link>
        </View>
      </View>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  brandContainer: {
    marginTop: spacing.xl,
    marginBottom: spacing.lg,
    alignItems: 'center',
  },
  logoBadge: {
    width: 60,
    height: 60,
    borderRadius: 18,
    backgroundColor: '#F0FDFA',
    borderWidth: 1,
    borderColor: '#CCFBF1',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  brandTitle: {
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: 1.4,
    color: colors.primary,
  },
  subtitle: {
    fontSize: 13,
    marginTop: 4,
    maxWidth: 260,
  },
  formCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  formHeading: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 2,
  },
  formSub: {
    fontSize: 13,
    marginBottom: spacing.lg,
  },
  submitButton: {
    marginTop: spacing.sm,
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.lg,
  },
  linkText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
});
