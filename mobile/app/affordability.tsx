import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation } from '@tanstack/react-query';
import { affordabilityApi } from '@/api/affordability';
import {
  AffordabilityResponse,
} from '@/types/affordability';
import { ApiErrorDetail } from '@/types/api';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { Icon } from '@/components/common/Icon';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { formatCurrency, formatMonthLabel, getTodayDateString } from '@/utils/format';

const affordabilitySchema = z.object({
  amount: z
    .string()
    .min(1, 'Amount is required')
    .refine((val) => !isNaN(Number(val)) && Number(val) > 0, {
      message: 'Amount must be greater than 0',
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

const TERM_PRESETS = ['3', '6', '12', '24'];

export default function AffordabilityScreen() {
  const router = useRouter();
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';
  const [apiError, setApiError] = useState<string | null>(null);

  const monthlyIncome = Number(user?.monthly_income || 0);
  const fixedExpenses = Number(user?.fixed_expenses || 0);
  const hasFinancialProfile = monthlyIncome > 0 || fixedExpenses > 0;

  const {
    control,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<AffordabilityFormData>({
    resolver: zodResolver(affordabilitySchema),
    defaultValues: {
      amount: '',
      start_date: getTodayDateString(),
      term_months: '12',
    },
  });

  const watchedAmount = watch('amount');
  const watchedTerm = watch('term_months');
  const numericAmount = Number(watchedAmount || 0);
  const numericTerm = Number(watchedTerm || 0);
  const estimatedMonthly =
    numericAmount > 0 && numericTerm > 0
      ? Math.round((numericAmount / numericTerm) * 100) / 100
      : 0;

  const mutation = useMutation<
    AffordabilityResponse,
    { statusCode: number; message: string; detail?: string | ApiErrorDetail[] },
    AffordabilityFormData
  >({
    mutationFn: async (data) => {
      return affordabilityApi.evaluateAffordability(data);
    },
    onError: (err) => {
      setApiError(err?.message || 'Failed to evaluate affordability analysis.');
    },
  });

  const onSubmit = (data: AffordabilityFormData) => {
    setApiError(null);
    mutation.mutate(data);
  };

  const result = mutation.data;

  const getVerdictStyle = (classification: string) => {
    switch (classification) {
      case 'Comfortable':
        return {
          badgeBg: '#F0FDFA',
          badgeBorder: '#CCFBF1',
          textColor: '#0F766E',
          cardBg: '#02262D',
          accent: '#2DD4BF',
        };
      case 'Manageable':
        return {
          badgeBg: '#F0FDF4',
          badgeBorder: '#DCFCE7',
          textColor: '#15803D',
          cardBg: '#02262D',
          accent: '#4ADE80',
        };
      case 'Risky':
        return {
          badgeBg: '#FFFBEB',
          badgeBorder: '#FEF3C7',
          textColor: '#B45309',
          cardBg: '#1C1917',
          accent: '#FBBF24',
        };
      case 'Not Affordable':
        return {
          badgeBg: '#FEF2F2',
          badgeBorder: '#FECACA',
          textColor: '#B91C1C',
          cardBg: '#1E1B1B',
          accent: '#F87171',
        };
      default:
        return {
          badgeBg: '#F8FAFC',
          badgeBorder: '#E2E8F0',
          textColor: colors.textPrimary,
          cardBg: '#02262D',
          accent: '#2DD4BF',
        };
    }
  };

  const verdictStyle = result ? getVerdictStyle(result.classification) : null;

  return (
    <ScreenWrapper>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* Top Navigation */}
        <View style={styles.topNav}>
          <TouchableOpacity
            onPress={() => router.back()}
            style={styles.backTouch}
            accessibilityRole="button"
            accessibilityLabel="Back"
          >
            <Icon name="arrow-left" size={20} color={colors.textPrimary} />
          </TouchableOpacity>
          <Typography style={styles.navTitle}>Affordability Simulator</Typography>
          <View style={{ width: 32 }} />
        </View>

        <View style={styles.headerBlock}>
          <Typography variant="caption" style={styles.kicker}>
            DECISION ENGINE
          </Typography>
          <Typography style={styles.screenHeading}>
            Test Purchase Fit
          </Typography>
          <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
            Simulate how a new loan, installment, or expense impacts your future cashflow.
          </Typography>
        </View>

        {/* Missing Financial Profile Warning */}
        {!hasFinancialProfile && (
          <TouchableOpacity
            activeOpacity={0.85}
            onPress={() => router.push('/(tabs)/profile' as any)}
            style={styles.profilePromptBanner}
          >
            <View style={styles.promptIconWrap}>
              <Icon name="settings" size={18} color="#0D9488" />
            </View>
            <View style={styles.promptTextCol}>
              <Typography style={styles.promptTitle}>
                Financial Profile Recommended
              </Typography>
              <Typography style={styles.promptDesc}>
                Set your monthly income and fixed expenses in Profile to get a calibrated decision verdict.
              </Typography>
            </View>
            <Icon name="chevron-right" size={16} tone="muted" />
          </TouchableOpacity>
        )}

        <ErrorBanner
          message={apiError}
          onDismiss={() => setApiError(null)}
        />

        {/* Interactive Simulation Form */}
        <View style={styles.formCard}>
          <Controller
            control={control}
            name="amount"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="Commitment / Purchase Total *"
                placeholder="0.00"
                keyboardType="decimal-pad"
                value={value}
                onChangeText={(text) => {
                  if (apiError) setApiError(null);
                  onChange(text);
                }}
                onBlur={onBlur}
                error={errors.amount?.message}
                helperText={
                  estimatedMonthly > 0
                    ? `Estimated monthly outflow: ${formatCurrency(estimatedMonthly, currency)}/mo`
                    : undefined
                }
              />
            )}
          />

          {/* Quick Term Presets */}
          <View style={styles.presetSection}>
            <Typography variant="label" style={styles.presetLabel}>
              Term Presets (Months)
            </Typography>
            <View style={styles.presetsRow}>
              {TERM_PRESETS.map((term) => {
                const isSelected = watchedTerm === term;
                return (
                  <TouchableOpacity
                    key={term}
                    activeOpacity={0.7}
                    onPress={() => setValue('term_months', term)}
                    style={[
                      styles.presetChip,
                      isSelected && styles.presetChipSelected,
                    ]}
                  >
                    <Typography
                      style={[
                        styles.presetChipText,
                        isSelected && styles.presetChipTextSelected,
                      ]}
                    >
                      {term} mo
                    </Typography>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={styles.row}>
            <View style={styles.halfCol}>
              <Controller
                control={control}
                name="term_months"
                render={({ field: { onChange, onBlur, value } }) => (
                  <Input
                    label="Custom Term *"
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
            </View>

            <View style={styles.halfCol}>
              <Controller
                control={control}
                name="start_date"
                render={({ field: { onChange, onBlur, value } }) => (
                  <Input
                    label="Start Date *"
                    placeholder="2026-09-01"
                    value={value}
                    onChangeText={(text) => {
                      if (apiError) setApiError(null);
                      onChange(text);
                    }}
                    onBlur={onBlur}
                    error={errors.start_date?.message}
                  />
                )}
              />
            </View>
          </View>

          <Button
            title="Evaluate Affordability"
            onPress={handleSubmit(onSubmit)}
            isLoading={mutation.isPending}
            style={styles.submitBtn}
          />
        </View>

        {/* Verdict & Impact Breakdown */}
        {result && verdictStyle && (
          <View style={styles.resultSection}>
            <View style={styles.resultHeadingRow}>
              <Typography style={styles.resultSectionHeading}>
                Verdict Analysis
              </Typography>
            </View>

            {/* Verdict Hero Card */}
            <View
              style={[
                styles.verdictCard,
                { backgroundColor: verdictStyle.cardBg },
              ]}
            >
              <View style={styles.verdictTopRow}>
                <View style={styles.verdictStatusCol}>
                  <Typography style={styles.verdictKicker}>
                    CLASSIFICATION
                  </Typography>
                  <Typography
                    style={[
                      styles.verdictTitle,
                      { color: verdictStyle.accent },
                    ]}
                  >
                    {result.classification}
                  </Typography>
                </View>

                <View
                  style={[
                    styles.verdictBadge,
                    {
                      backgroundColor: verdictStyle.badgeBg,
                      borderColor: verdictStyle.badgeBorder,
                    },
                  ]}
                >
                  <Typography
                    style={[
                      styles.verdictBadgeText,
                      { color: verdictStyle.textColor },
                    ]}
                  >
                    {result.worst_buffer_percentage}% Margin
                  </Typography>
                </View>
              </View>

              <Typography style={styles.verdictExplanation}>
                {result.explanation}
              </Typography>

              <View style={styles.verdictDivider} />

              <View style={styles.verdictMetricsGrid}>
                <View style={styles.verdictMetric}>
                  <Typography style={styles.verdictMetricLabel}>
                    WORST BUFFER
                  </Typography>
                  <Typography
                    style={[
                      styles.verdictMetricValue,
                      { color: verdictStyle.accent },
                    ]}
                  >
                    {formatCurrency(result.worst_projected_buffer, currency)}
                  </Typography>
                </View>

                <View style={styles.verdictMetricDivider} />

                <View style={styles.verdictMetric}>
                  <Typography style={styles.verdictMetricLabel}>
                    BOTTLENECK MONTH
                  </Typography>
                  <Typography style={styles.verdictMetricValueLight}>
                    {formatMonthLabel(result.worst_month)}
                  </Typography>
                </View>
              </View>
            </View>

            {/* Monthly Breakdown Timeline */}
            <View style={styles.breakdownSection}>
              <Typography style={styles.breakdownHeading}>
                Commitment Period Impact
              </Typography>

              <View style={styles.breakdownList}>
                {result.monthly_results.map((m) => {
                  const isNeg = Number(m.projected_buffer) < 0;
                  return (
                    <View key={m.month} style={styles.breakdownCard}>
                      <View style={styles.breakdownHeader}>
                        <Typography style={styles.breakdownMonth}>
                          {formatMonthLabel(m.month)}
                        </Typography>
                        <Typography
                          style={[
                            styles.breakdownBuffer,
                            isNeg && styles.breakdownBufferDanger,
                          ]}
                        >
                          {formatCurrency(m.projected_buffer, currency)} buffer
                        </Typography>
                      </View>

                      <View style={styles.breakdownSub}>
                        <Typography style={styles.breakdownPayment}>
                          Installment: {formatCurrency(m.proposed_commitment_amount, currency)}
                        </Typography>
                        <Typography
                          style={[
                            styles.breakdownStatus,
                            isNeg && styles.breakdownStatusDanger,
                          ]}
                        >
                          {isNeg ? 'Deficit' : 'Sustainable'}
                        </Typography>
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          </View>
        )}

        <View style={styles.bottomSpacer} />
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxl,
    flexGrow: 1,
  },
  topNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
  },
  backTouch: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F1F5F9',
    alignItems: 'center',
    justifyContent: 'center',
  },
  navTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  headerBlock: {
    marginBottom: spacing.lg,
  },
  kicker: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.8,
    color: colors.textMuted,
    marginBottom: 2,
  },
  screenHeading: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.textPrimary,
    letterSpacing: -0.3,
  },
  subtitle: {
    marginTop: spacing.xs / 2,
    lineHeight: 19,
  },
  profilePromptBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F0FDFA',
    borderRadius: 16,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: '#CCFBF1',
    marginBottom: spacing.lg,
  },
  promptIconWrap: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: '#CCFBF1',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  promptTextCol: {
    flex: 1,
    marginRight: spacing.sm,
  },
  promptTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0F766E',
    marginBottom: 2,
  },
  promptDesc: {
    fontSize: 11,
    lineHeight: 16,
    color: '#115E59',
  },
  formCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xl,
  },
  presetSection: {
    marginBottom: spacing.md,
  },
  presetLabel: {
    marginBottom: spacing.xs,
    fontSize: 12,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  presetsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  presetChip: {
    flex: 1,
    paddingVertical: spacing.sm,
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  presetChipSelected: {
    backgroundColor: '#F0FDFA',
    borderColor: '#2DD4BF',
  },
  presetChipText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  presetChipTextSelected: {
    color: colors.primary,
    fontWeight: '700',
  },
  row: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  halfCol: {
    flex: 1,
  },
  submitBtn: {
    marginTop: spacing.sm,
  },
  resultSection: {
    marginBottom: spacing.xl,
  },
  resultHeadingRow: {
    marginBottom: spacing.md,
  },
  resultSectionHeading: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  verdictCard: {
    borderRadius: 20,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  verdictTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
  },
  verdictStatusCol: {
    flex: 1,
  },
  verdictKicker: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
    color: '#94A3B8',
    marginBottom: 2,
  },
  verdictTitle: {
    fontSize: 24,
    fontWeight: '700',
  },
  verdictBadge: {
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 4,
    borderRadius: borderRadius.full,
    borderWidth: 1,
  },
  verdictBadgeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  verdictExplanation: {
    fontSize: 13,
    lineHeight: 19,
    color: '#E2E8F0',
    marginBottom: spacing.md,
  },
  verdictDivider: {
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    marginBottom: spacing.md,
  },
  verdictMetricsGrid: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  verdictMetric: {
    flex: 1,
  },
  verdictMetricDivider: {
    width: 1,
    height: 24,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    marginHorizontal: spacing.md,
  },
  verdictMetricLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.6,
    color: '#94A3B8',
    marginBottom: 2,
  },
  verdictMetricValue: {
    fontSize: 15,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  verdictMetricValueLight: {
    fontSize: 14,
    fontWeight: '600',
    color: '#F1F5F9',
  },
  breakdownSection: {
    marginTop: spacing.xs,
  },
  breakdownHeading: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  breakdownList: {
    gap: spacing.sm,
  },
  breakdownCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  breakdownHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  breakdownMonth: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  breakdownBuffer: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.primary,
    fontVariant: ['tabular-nums'],
  },
  breakdownBufferDanger: {
    color: colors.error,
  },
  breakdownSub: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  breakdownPayment: {
    fontSize: 12,
    color: colors.textSecondary,
  },
  breakdownStatus: {
    fontSize: 11,
    fontWeight: '600',
    color: '#10B981',
  },
  breakdownStatusDanger: {
    color: colors.error,
  },
  bottomSpacer: {
    height: spacing.xl,
  },
});
