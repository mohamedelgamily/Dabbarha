import React from 'react';
import { View, StyleSheet, ScrollView, RefreshControl } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/dashboard';
import { ApiErrorDetail } from '@/types/api';
import { DashboardSummaryResponse } from '@/types/dashboard';
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

interface MetricCardProps {
  label: string;
  value: string;
  icon: string;
  valueColor: string;
  variant?: 'default' | 'warning';
}

function MetricCard({ label, value, icon, valueColor, variant = 'default' }: MetricCardProps) {
  return (
    <Card
      style={[
        styles.metricCard,
        variant === 'warning' && styles.warningMetricCard,
      ]}
      variant={variant === 'warning' ? 'outlined' : 'elevated'}
    >
      <Typography variant="caption" color={colors.textSecondary} style={styles.metricLabel}>
        {icon} {label}
      </Typography>
      <Typography
        variant="h2"
        color={valueColor}
        style={styles.metricValue}
      >
        {value}
      </Typography>
    </Card>
  );
}

export default function DashboardScreen() {
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';

  const {
    data: summary,
    isLoading,
    isError,
    error,
    refetch,
    isRefetching,
  } = useQuery<DashboardSummaryResponse, { statusCode: number; message: string; detail?: string | ApiErrorDetail[] }>({
    queryKey: ['dashboard-summary'],
    queryFn: dashboardApi.getDashboardSummary,
  });

  if (isLoading && !isRefetching) {
    return (
      <ScreenWrapper>
        <View style={styles.header}>
          <Typography variant="h1">Dashboard</Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Financial Overview
          </Typography>
        </View>
        <LoadingIndicator message="Loading dashboard..." />
      </ScreenWrapper>
    );
  }

  if (isError) {
    return (
      <ScreenWrapper scrollable>
        <View style={styles.header}>
          <Typography variant="h1">Dashboard</Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Financial Overview
          </Typography>
        </View>
        <ErrorBanner
          message={
            error?.message ||
            'Failed to load dashboard. Please check your connection.'
          }
        />
        <Button title="Try Again" onPress={() => refetch()} style={styles.retryButton} />
      </ScreenWrapper>
    );
  }

  const isNegative = summary?.has_current_month_negative_buffer ?? false;

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
          <Typography variant="h1">Dashboard</Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Financial Overview
          </Typography>
        </View>

        <View style={styles.metricsContainer}>
          <MetricCard
            label="Monthly Income"
            value={formatCurrency(summary?.monthly_income || '0.00', currency)}
            icon="💰"
            valueColor={colors.success}
          />
          <MetricCard
            label="Fixed Expenses"
            value={formatCurrency(summary?.fixed_expenses || '0.00', currency)}
            icon="📊"
            valueColor={colors.secondary}
          />
          <MetricCard
            label="Current Month Obligations"
            value={formatCurrency(summary?.current_month_obligation_payments || '0.00', currency)}
            icon="📋"
            valueColor={colors.primary}
          />
          <MetricCard
            label="Projected Buffer"
            value={formatCurrency(summary?.current_month_projected_buffer || '0.00', currency)}
            icon={isNegative ? '⚠️' : '💵'}
            valueColor={isNegative ? colors.error : colors.success}
            variant={isNegative ? 'warning' : 'default'}
          />
          <MetricCard
            label="Active Obligations"
            value={String(summary?.active_obligations_count ?? 0)}
            icon="📁"
            valueColor={colors.secondary}
          />
        </View>

        {isNegative && (
          <Card style={styles.warningCard} variant="outlined">
            <Typography variant="body" color={colors.error} style={styles.warningText}>
              ⚠️ Your projected buffer is negative this month. Review your obligations to avoid over-committing.
            </Typography>
          </Card>
        )}
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
  metricsContainer: {
    gap: spacing.md,
  },
  metricCard: {
    padding: spacing.md,
  },
  warningMetricCard: {
    borderColor: colors.error,
    backgroundColor: colors.errorLight,
  },
  metricLabel: {
    marginBottom: spacing.sm,
  },
  metricValue: {
    fontSize: typography.sizes.xxl,
  },
  retryButton: {
    marginTop: spacing.md,
  },
  warningCard: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderColor: colors.error,
    backgroundColor: colors.errorLight,
  },
  warningText: {
    lineHeight: 22,
  },
});
