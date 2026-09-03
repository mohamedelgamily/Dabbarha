import React from 'react';
import { View, StyleSheet, ScrollView, RefreshControl } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { forecastApi } from '@/api/forecast';
import { ApiErrorDetail } from '@/types/api';
import { ForecastResponse } from '@/types/forecast';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Card } from '@/components/common/Card';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Button } from '@/components/common/Button';
import { colors, spacing, typography } from '@/constants/theme';

function formatCurrency(value: string, currency: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) {
    return `${value} ${currency}`;
  }
  return `${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatMonthLabel(monthStr: string): string {
  const [year, month] = monthStr.split('-').map(Number);
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function getCurrentMonthStartDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}-01`;
}

interface ForecastMonthCardProps {
  month: string;
  income: string;
  fixedExpenses: string;
  obligationPayments: string;
  projectedBuffer: string;
  hasNegativeBuffer: boolean;
  currency: string;
}

function ForecastMonthCard({
  month,
  income,
  fixedExpenses,
  obligationPayments,
  projectedBuffer,
  hasNegativeBuffer,
  currency,
}: ForecastMonthCardProps) {
  return (
    <Card
      style={[styles.monthCard, hasNegativeBuffer && styles.negativeMonthCard]}
      variant={hasNegativeBuffer ? 'outlined' : 'elevated'}
    >
      <View style={styles.monthHeader}>
        <Typography variant="h3" style={styles.monthLabel}>
          {formatMonthLabel(month)}
        </Typography>
        {hasNegativeBuffer && (
          <Typography variant="caption" color={colors.error}>
            ⚠️ Negative
          </Typography>
        )}
      </View>
      <View style={styles.detailsContainer}>
        <View style={styles.detailRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Income
          </Typography>
          <Typography variant="bodyBold" color={colors.success}>
            {formatCurrency(income, currency)}
          </Typography>
        </View>
        <View style={styles.detailRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Fixed Expenses
          </Typography>
          <Typography variant="bodyBold" color={colors.secondary}>
            {formatCurrency(fixedExpenses, currency)}
          </Typography>
        </View>
        <View style={styles.detailRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Obligations
          </Typography>
          <Typography variant="bodyBold" color={colors.primary}>
            {formatCurrency(obligationPayments, currency)}
          </Typography>
        </View>
        <View style={[styles.detailRow, styles.bufferRow]}>
          <Typography variant="caption" color={colors.textSecondary}>
            Projected Buffer
          </Typography>
          <Typography
            variant="bodyBold"
            color={hasNegativeBuffer ? colors.error : colors.success}
          >
            {formatCurrency(projectedBuffer, currency)}
          </Typography>
        </View>
      </View>
    </Card>
  );
}

export default function ForecastScreen() {
  const router = useRouter();
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';

  const startMonth = getCurrentMonthStartDate();
  const months = 6;

  const {
    data: forecast,
    isLoading,
    isError,
    error,
    refetch,
    isRefetching,
  } = useQuery<ForecastResponse, { statusCode: number; message: string; detail?: string | ApiErrorDetail[] }>({
    queryKey: ['forecast', startMonth, months],
    queryFn: () => forecastApi.getForecast({ start_month: startMonth, months }),
  });

  if (isLoading && !isRefetching) {
    return (
      <ScreenWrapper>
        <View style={styles.header}>
          <Typography variant="h1">Forecast</Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Cash-Flow Projection
          </Typography>
        </View>
        <LoadingIndicator message="Loading forecast..." />
      </ScreenWrapper>
    );
  }

  if (isError) {
    return (
      <ScreenWrapper scrollable>
        <View style={styles.header}>
          <Typography variant="h1">Forecast</Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Cash-Flow Projection
          </Typography>
        </View>
        <ErrorBanner
          message={
            error?.message ||
            'Failed to load forecast. Please check your connection.'
          }
        />
        <Button title="Try Again" onPress={() => refetch()} style={styles.retryButton} />
      </ScreenWrapper>
    );
  }

  const hasAnyNegative = forecast?.rows?.some((row) => row.has_negative_buffer) ?? false;

  return (
    <ScreenWrapper>
      <ScrollView
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <Typography variant="h1">Forecast</Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Cash-Flow Projection
          </Typography>
        </View>

        {hasAnyNegative && (
          <Card style={styles.warningCard} variant="outlined">
            <Typography variant="body" color={colors.error} style={styles.warningText}>
              ⚠️ Some months have a negative projected buffer. Review your obligations to avoid over-committing.
            </Typography>
          </Card>
        )}

        <View style={styles.monthsContainer}>
          {forecast?.rows?.map((row) => (
            <ForecastMonthCard
              key={row.month}
              month={row.month}
              income={row.income}
              fixedExpenses={row.fixed_expenses}
              obligationPayments={row.obligation_payments}
              projectedBuffer={row.projected_buffer}
              hasNegativeBuffer={row.has_negative_buffer}
              currency={currency}
            />
          ))}
        </View>

        <Button
          title="Back to Dashboard"
          variant="secondary"
          onPress={() => router.back()}
          style={styles.backButton}
        />
      </ScrollView>
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
  scrollContent: {
    padding: spacing.md,
  },
  monthsContainer: {
    gap: spacing.md,
  },
  monthCard: {
    padding: spacing.md,
  },
  negativeMonthCard: {
    borderColor: colors.error,
    backgroundColor: colors.errorLight,
  },
  monthHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  monthLabel: {
    fontSize: typography.sizes.lg,
  },
  detailsContainer: {
    gap: spacing.sm,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  bufferRow: {
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  warningCard: {
    marginBottom: spacing.md,
    padding: spacing.md,
    borderColor: colors.error,
    backgroundColor: colors.errorLight,
  },
  warningText: {
    lineHeight: 22,
  },
  retryButton: {
    marginTop: spacing.md,
  },
  backButton: {
    marginTop: spacing.lg,
  },
});
