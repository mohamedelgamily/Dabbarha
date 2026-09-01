import React, { useState } from 'react';
import { View, StyleSheet, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation } from '@tanstack/react-query';
import { affordabilityApi } from '@/api/affordability';
import {
  AffordabilityRequest,
  AffordabilityResponse,
} from '@/types/affordability';
import { ApiErrorDetail } from '@/types/api';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Card } from '@/components/common/Card';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { colors, spacing, typography } from '@/constants/theme';

const affordabilitySchema = z.object({
  amount: z
    .string()
    .min(1, 'Amount is required')
    .refine((val) => !isNaN(Number(val)) && Number(val) >= 0, {
      message: 'Amount must be 0 or greater',
    }),
  start_date: z
    .string()
    .min(1, 'Start date is required')
    .regex(/^\d{4}-\d{2}-\d{2}$/, 'Date must be in YYYY-MM-DD format'),
  term_months: z
    .string()
    .min(1, 'Term is required')
    .refine((val) => !isNaN(Number(val)) && Number(val) > 0, {
      message: 'Term must be greater than 0',
    }),
});

type AffordabilityFormData = z.infer<typeof affordabilitySchema>;

function formatCurrency(value: string, currency: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) {
    return `${value} ${currency}`;
  }
  return `${num.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`;
}

function formatMonthLabel(monthStr: string): string {
  const [year, month] = monthStr.split('-').map(Number);
  const date = new Date(year, month - 1, 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function getTodayDateString(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getClassificationColor(
  classification: string,
): keyof typeof colors {
  switch (classification) {
    case 'Comfortable':
      return 'success';
    case 'Manageable':
      return 'primary';
    case 'Risky':
      return 'warning';
    case 'Not Affordable':
      return 'error';
    default:
      return 'textSecondary';
  }
}

interface MonthlyResultCardProps {
  result: AffordabilityResponse['monthly_results'][0];
  currency: string;
}

function MonthlyResultCard({ result, currency }: MonthlyResultCardProps) {
  const buffer = parseFloat(result.projected_buffer);
  const isNegative = buffer < 0;

  return (
    <Card
      style={[styles.monthCard, isNegative && styles.negativeMonthCard]}
      variant={isNegative ? 'outlined' : 'elevated'}
    >
      <View style={styles.monthHeader}>
        <Typography variant="bodyBold">{formatMonthLabel(result.month)}</Typography>
        {isNegative && (
          <Typography variant="caption" color={colors.error}>
            ⚠️ Negative
          </Typography>
        )}
      </View>
      <View style={styles.monthDetails}>
        <View style={styles.detailRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Proposed Payment
          </Typography>
          <Typography variant="body">
            {formatCurrency(result.proposed_commitment_amount, currency)}
          </Typography>
        </View>
        <View style={styles.detailRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Projected Buffer
          </Typography>
          <Typography
            variant="bodyBold"
            color={isNegative ? colors.error : colors.success}
          >
            {formatCurrency(result.projected_buffer, currency)}
          </Typography>
        </View>
      </View>
    </Card>
  );
}

export default function AffordabilityScreen() {
  const router = useRouter();
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<AffordabilityFormData>({
    resolver: zodResolver(affordabilitySchema),
    defaultValues: {
      amount: '',
      start_date: getTodayDateString(),
      term_months: '12',
    },
  });

  const mutation = useMutation<
    AffordabilityResponse,
    { statusCode: number; message: string; detail?: string | ApiErrorDetail[] },
    AffordabilityFormData
  >({
    mutationFn: async (data) => {
      return affordabilityApi.evaluateAffordability(data);
    },
    onError: (err) => {
      setApiError(err?.message || 'Failed to evaluate affordability.');
    },
  });

  const onSubmit = (data: AffordabilityFormData) => {
    setApiError(null);
    mutation.mutate(data);
  };

  const result: AffordabilityResponse | undefined = mutation.data;
  const classificationColor = result
    ? getClassificationColor(result.classification)
    : 'textSecondary';

  return (
    <ScreenWrapper>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <Typography variant="h1">Affordability</Typography>
          <Typography
            variant="body"
            color={colors.textSecondary}
            style={styles.subtitle}
          >
            Check if you can afford a new commitment
          </Typography>
        </View>

        <ErrorBanner
          message={apiError}
          onDismiss={() => setApiError(null)}
        />

        <Card style={styles.formCard}>
          <Controller
            control={control}
            name="amount"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="Commitment Amount *"
                placeholder="0.00"
                keyboardType="decimal-pad"
                value={value}
                onChangeText={(text) => {
                  if (apiError) setApiError(null);
                  onChange(text);
                }}
                onBlur={onBlur}
                error={errors.amount?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="start_date"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="Start Date (YYYY-MM-DD) *"
                placeholder="2026-09-01"
                value={value}
                onChangeText={(text) => {
                  if (apiError) setApiError(null);
                  onChange(text);
                }}
                onBlur={onBlur}
                error={errors.start_date?.message}
                helperText="Format: YYYY-MM-DD"
              />
            )}
          />

          <Controller
            control={control}
            name="term_months"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="Term (Months) *"
                placeholder="12"
                keyboardType="number-pad"
                value={value}
                onChangeText={(text) => {
                  if (apiError) setApiError(null);
                  onChange(text);
                }}
                onBlur={onBlur}
                error={errors.term_months?.message}
              />
            )}
          />

          <Button
            title="Check Affordability"
            onPress={handleSubmit(onSubmit)}
            isLoading={mutation.isPending}
            style={styles.submitButton}
          />
        </Card>

        {result && (
          <View style={styles.resultSection}>
            <Typography variant="h2" style={styles.sectionTitle}>
              Result
            </Typography>

            <Card style={styles.resultCard}>
              <View style={styles.classificationRow}>
                <Typography variant="body" color={colors.textSecondary}>
                  Classification
                </Typography>
                <Typography
                  variant="h3"
                  color={colors[classificationColor]}
                >
                  {result.classification}
                </Typography>
              </View>

              <Typography
                variant="body"
                color={colors.textSecondary}
                style={styles.explanation}
              >
                {result.explanation}
              </Typography>

              <View style={styles.resultDetails}>
                <View style={styles.resultRow}>
                  <Typography variant="caption" color={colors.textSecondary}>
                    Worst Projected Buffer
                  </Typography>
                  <Typography variant="bodyBold">
                    {formatCurrency(result.worst_projected_buffer, currency)}
                  </Typography>
                </View>
                <View style={styles.resultRow}>
                  <Typography variant="caption" color={colors.textSecondary}>
                    Worst Buffer Percentage
                  </Typography>
                  <Typography variant="bodyBold">
                    {result.worst_buffer_percentage}%
                  </Typography>
                </View>
                <View style={styles.resultRow}>
                  <Typography variant="caption" color={colors.textSecondary}>
                    Worst Month
                  </Typography>
                  <Typography variant="bodyBold">
                    {formatMonthLabel(result.worst_month)}
                  </Typography>
                </View>
              </View>
            </Card>

            <Typography variant="h3" style={styles.breakdownTitle}>
              Monthly Breakdown
            </Typography>

            <View style={styles.monthsContainer}>
              {result.monthly_results.map((monthResult) => (
                <MonthlyResultCard
                  key={monthResult.month}
                  result={monthResult}
                  currency={currency}
                />
              ))}
            </View>
          </View>
        )}

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
  scrollContent: {
    padding: spacing.md,
  },
  header: {
    marginVertical: spacing.md,
  },
  subtitle: {
    marginTop: spacing.xs,
  },
  formCard: {
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  submitButton: {
    marginTop: spacing.md,
  },
  resultSection: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    marginBottom: spacing.md,
  },
  resultCard: {
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  classificationRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  explanation: {
    marginBottom: spacing.md,
    lineHeight: 22,
  },
  resultDetails: {
    gap: spacing.sm,
  },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  breakdownTitle: {
    marginBottom: spacing.md,
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
  monthDetails: {
    gap: spacing.xs,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  backButton: {
    marginTop: spacing.lg,
  },
});
