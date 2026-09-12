import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { forecastApi } from '@/api/forecast';
import { ApiErrorDetail } from '@/types/api';
import { ForecastResponse, ForecastMonthResponse } from '@/types/forecast';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Icon } from '@/components/common/Icon';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { colors, typography } from '@/constants/theme';
import { formatCurrency, formatMonthLabel, getCurrentMonthStartDate } from '@/utils/format';

export default function ForecastScreen() {
  const router = useRouter();
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';

  const startMonth = getCurrentMonthStartDate();
  const months = 6;

  const [selectedMonthIndex, setSelectedMonthIndex] = useState<number>(0);

  const {
    data: forecast,
    isLoading,
    isError,
    error,
    refetch,
    isRefetching,
  } = useQuery<
    ForecastResponse,
    { statusCode: number; message: string; detail?: string | ApiErrorDetail[] }
  >({
    queryKey: ['forecast', startMonth, months],
    queryFn: () => forecastApi.getForecast({ start_month: startMonth, months }),
  });

  if (isLoading && !isRefetching) {
    return (
      <ScreenWrapper backgroundColor={colors.primary} statusBarStyle="light">
        <View style={styles.topNav}>
          <TouchableOpacity
            onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}
            style={styles.backTouch}
            accessibilityRole="button"
            accessibilityLabel="Back"
          >
            <Icon name="arrow-left" size={20} color="#E3EDE4" />
          </TouchableOpacity>
          <View style={styles.navCopy}><Typography style={styles.navTitle}>Cashflow Forecast</Typography><Typography style={styles.navSubtitle}>See your financial runway ahead</Typography></View>
          <View style={{ width: 36 }} />
        </View>
        <View style={{ flex: 1, backgroundColor: "#F6F4EF" }}><LoadingIndicator message="Loading cashflow forecast..." /></View>
      </ScreenWrapper>
    );
  }

  if (isError) {
    return (
      <ScreenWrapper scrollable backgroundColor={colors.primary} statusBarStyle="light">
        <View style={styles.topNav}>
          <TouchableOpacity
            onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}
            style={styles.backTouch}
            accessibilityRole="button"
            accessibilityLabel="Back"
          >
            <Icon name="arrow-left" size={20} color="#E3EDE4" />
          </TouchableOpacity>
          <View style={styles.navCopy}><Typography style={styles.navTitle}>Cashflow Forecast</Typography><Typography style={styles.navSubtitle}>See your financial runway ahead</Typography></View>
          <View style={{ width: 36 }} />
        </View>
        <ErrorBanner
          message={
            error?.message ||
            'Unable to load forecast data. Please check your connection.'
          }
        />
        <Button
          title="Try Again" variant="secondary"
          onPress={() => refetch()}
          style={styles.retryButton}
        />
      </ScreenWrapper>
    );
  }

  const rows = forecast?.rows || [];
  const hasIncome = user?.monthly_income != null && Number(user.monthly_income) > 0;
  const hasAnyNegative = rows.some((r) => r.has_negative_buffer);

  // Chart geometry only: use the same magnitude scale and zero line for all months.
  // Without income, visualize known outflows instead of implying forecast accuracy.
  const chartValues = rows.map((row) => hasIncome
    ? Number(row.projected_buffer || 0)
    : -(Number(row.fixed_expenses || 0) + Number(row.obligation_payments || 0)));
  const maxBuffer = Math.max(1, ...chartValues.map(Math.abs));
  const hasPositive = chartValues.some((value) => value > 0);
  const hasNegative = chartValues.some((value) => value < 0);
  const baseline = hasNegative ? (hasPositive ? 36 : 0) : 72;
  const positiveSpace = baseline;
  const negativeSpace = 72 - baseline;
  const selectedRow: ForecastMonthResponse | undefined = rows[selectedMonthIndex] || rows[0];

  return (
    <ScreenWrapper backgroundColor={colors.primary} statusBarStyle="light">
      <ScrollView
        style={{ backgroundColor: '#F6F4EF' }}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        {/* Top Header */}
        <View style={styles.topNav}>
          <TouchableOpacity
            onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}
            style={styles.backTouch}
            accessibilityRole="button"
            accessibilityLabel="Back"
          >
            <Icon name="arrow-left" size={20} color="#E3EDE4" />
          </TouchableOpacity>
          <View style={styles.navCopy}><Typography style={styles.navTitle}>Cashflow Forecast</Typography><Typography style={styles.navSubtitle}>See your financial runway ahead</Typography></View>
          <View style={{ width: 36 }} />
        </View>

        <View style={styles.headerBlock}>
          <View style={styles.rangePill}><Typography style={styles.rangeLabel}>{months} Months</Typography></View>
          <Typography style={styles.runwayTitle}>Financial Runway</Typography>
        </View>
        {/* Hero Trajectory Visualizer */}
        <View style={styles.heroTrajectoryCard}>
          <View style={styles.heroTopRow}>
            <View style={styles.heroHeaderCol}>
              <Typography style={styles.heroKicker}>{hasIncome ? 'Projected Net Surplus' : 'Known Monthly Commitments'}</Typography>
              <Typography style={[styles.heroAmount, hasIncome && selectedRow?.has_negative_buffer && styles.amountNegative]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.45} accessibilityLiveRegion="polite">
                {selectedRow ? formatCurrency(hasIncome ? selectedRow.projected_buffer
                  : Number(selectedRow.fixed_expenses || 0) + Number(selectedRow.obligation_payments || 0), currency) : 'No forecast data'}
              </Typography>
              {!hasIncome && <Typography style={styles.chartNote}>Outflows only Â· income not configured</Typography>}
              {hasIncome && selectedRow?.has_negative_buffer && <Typography style={styles.amountNegative}>Projected deficit</Typography>}
            </View>
            {selectedRow && <View style={styles.monthPill}><Typography style={styles.monthPillText}>{formatMonthLabel(selectedRow.month)}</Typography></View>}
          </View>
          {/* Interactive Runway Visual Progression Bars */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.runwayBarsContainer}>
            {rows.map((row, idx) => {
              const value = chartValues[idx];
              const negative = value < 0;
              const height = Math.abs(value) / maxBuffer * (negative ? negativeSpace : positiveSpace);
              const selected = row.month === selectedRow?.month;
              return <TouchableOpacity key={row.month} onPress={() => setSelectedMonthIndex(idx)} style={styles.barColumn}
                accessibilityRole="button" accessibilityState={{ selected }}
                accessibilityLabel={formatMonthLabel(row.month) + ': ' + (hasIncome ? 'projected buffer ' : 'known outflows ') + formatCurrency(hasIncome ? value : Math.abs(value), currency)}>
                <View style={[styles.barTrack, selected && styles.trackSelected]}>
                  <View style={[styles.zeroLine, { top: baseline }]} />
                  {value === 0 ? <View style={[styles.zeroDot, { top: baseline - 3 }]} /> :
                    <View style={[styles.barFill, {
                      height, top: negative ? baseline : baseline - height,
                      backgroundColor: !hasIncome ? '#8CB6AE' : negative ? '#C27F70' : selected ? '#8ED8BF' : '#3C9682',
                    }]} />}
                </View>
                <Typography style={[styles.monthBarLabel, selected && styles.monthBarLabelSelected]}>{formatMonthLabel(row.month).split(' ')[0]}</Typography>
                <Typography style={styles.barYear}>{row.month.slice(0, 4)}</Typography>
              </TouchableOpacity>;
            })}
          </ScrollView>
          {rows.length > 0 && <Typography style={styles.scaleLabel}>
            Shared scale Â· {formatCurrency(maxBuffer, currency)} {hasPositive && hasNegative ? 'either side of zero' : 'from zero'}
          </Typography>}
          {/* Selected Month Financial Equation Breakdown */}
          {selectedRow && (
            <View style={styles.equationGrid}>
              <View style={styles.equationItem}>
                <View style={styles.metricHeading}><Icon name="arrow-up" size={13} color="#91CBB4" /><Typography style={styles.equationLabel}>Income</Typography></View>
                <Typography style={styles.equationValueSuccess}>
                  {hasIncome ? formatCurrency(selectedRow.income, currency) : 'Not configured'}
                </Typography>
              </View>

              <View style={styles.equationDivider} />

              <View style={styles.equationItem}>
                <View style={styles.metricHeading}><Icon name="arrow-down" size={13} color="#D1AF87" /><Typography style={styles.equationLabel}>Fixed Expenses</Typography></View>
                <Typography style={styles.equationValue}>
                  {formatCurrency(selectedRow.fixed_expenses, currency)}
                </Typography>
              </View>

              <View style={styles.equationDivider} />

              <View style={styles.equationItem}>
                <View style={styles.metricHeading}><Icon name="credit-card" size={13} color="#96BAC5" /><Typography style={styles.equationLabel}>Obligations</Typography></View>
                <Typography style={styles.equationValue}>
                  {formatCurrency(selectedRow.obligation_payments, currency)}
                </Typography>
              </View>
            </View>
          )}
        </View>

        {!hasIncome && <TouchableOpacity onPress={() => router.push('/(tabs)/profile')} style={styles.profilePromptBanner} accessibilityRole="button">
          <View style={styles.promptIconWrap}><Icon name="settings" size={20} color="#447B68" /></View>
          <View style={styles.promptTextCol}>
            <Typography style={styles.promptTitle}>Complete your financial profile</Typography>
            <Typography style={styles.promptDesc}>Add monthly income and fixed expenses to generate an accurate cashflow forecast.</Typography>
            <Typography style={styles.profileLink}>Set up profile â†’</Typography>
          </View>
        </TouchableOpacity>}
        {hasIncome && hasAnyNegative && (
          <View style={styles.warningBanner}>
            <View style={styles.warningIconWrap}>
              <Icon name="alert-triangle" size={18} color={colors.error} />
            </View>
            <View style={styles.warningContent}>
              <Typography style={styles.warningTitle}>
                Potential Deficit Detected
              </Typography>
              <Typography style={styles.warningDesc}>
                One or more upcoming months project commitments exceeding monthly income.
              </Typography>
            </View>
          </View>
        )}

        {/* Timeline Sequence */}
        <View style={styles.timelineSection}>
          <Typography style={styles.timelineSectionTitle}>
            Monthly Breakdown
          </Typography>

          <View style={styles.timelineList}>{rows.length === 0 && <Typography style={styles.timelineMeta}>No forecast months were returned for this period.</Typography>}
            {rows.map((row, idx) => {
              const isNeg = row.has_negative_buffer;
              const totalOutflow =
                Number(row.fixed_expenses || 0) +
                Number(row.obligation_payments || 0);

              return (
                <View key={row.month} style={styles.timelineItem}>
                  <View style={styles.timelineLeft}>
                    <View
                      style={[
                        styles.timelineDot,
                        !hasIncome || Number(row.projected_buffer) === 0 ? styles.dotNeutral : isNeg ? styles.dotDanger : styles.dotSuccess,
                      ]}
                    />
                    {idx < rows.length - 1 && <View style={styles.timelineLine} />}
                  </View>

                  <TouchableOpacity style={[styles.timelineCard, row.month === selectedRow?.month && styles.timelineSelected]} onPress={() => setSelectedMonthIndex(idx)} accessibilityRole="button" accessibilityState={{ selected: row.month === selectedRow?.month }}>
                    <View style={styles.timelineHeader}>
                      <Typography style={styles.timelineMonth}>
                        {formatMonthLabel(row.month)}
                      </Typography>
                      <Typography
                        style={[
                          styles.timelineBufferValue,
                          hasIncome && isNeg && styles.timelineBufferDanger,
                        ]}
                      >
                        {hasIncome ? formatCurrency(row.projected_buffer, currency) : 'Income not set'}
                      </Typography>
                    </View>

                    <View style={styles.timelineSubRow}>
                      <Typography style={styles.timelineMeta}>
                        Committed: {formatCurrency(totalOutflow, currency)}
                      </Typography>
                      <Typography style={[styles.timelineStatus, !hasIncome || Number(row.projected_buffer) === 0 ? styles.pillNeutral : isNeg ? styles.pillDanger : styles.pillSuccess]}>
                        {!hasIncome ? 'Outflows only' : isNeg ? 'Deficit' : Number(row.projected_buffer) === 0 ? 'Break-even' : 'Safe buffer'}
                      </Typography>
                    </View>
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>
        </View>

        <View style={styles.bottomSpacer} />
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  scrollContent: { flexGrow: 1, paddingBottom: 30 },
  topNav: { flexDirection: 'row', alignItems: 'center', gap: 9, backgroundColor: '#02262D', paddingHorizontal: 16, paddingTop: 10, paddingBottom: 18 },
  navCopy: { flex: 1 },
  backTouch: { width: 36, height: 44, borderRadius: 20, backgroundColor: '#173F40', alignItems: 'center', justifyContent: 'center' },
  navTitle: { ...typography.title, fontSize: 23, lineHeight: 29, color: '#F6F6EB', textAlign: 'center' },
  navSubtitle: { fontSize: 11, lineHeight: 17, color: '#B4C9C2', textAlign: 'center', marginTop: 3 },
  headerBlock: { backgroundColor: '#123D3E', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, paddingVertical: 7 },
  rangePill: { paddingHorizontal: 22, paddingVertical: 8, backgroundColor: '#F2F4EB', borderRadius: 22 },
  rangeLabel: { fontSize: 12, lineHeight: 18, color: '#204C46' },
  runwayTitle: { ...typography.title, flex: 1, textAlign: 'center', fontSize: 14, color: '#BDCEC4' },
  heroTrajectoryCard: { backgroundColor: '#022E32', borderBottomLeftRadius: 26, borderBottomRightRadius: 26, paddingHorizontal: 19, paddingTop: 18, paddingBottom: 14, marginBottom: 20 },
  heroTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 9, marginBottom: 8 },
  heroHeaderCol: { flex: 1, minWidth: 0 },
  heroKicker: { fontSize: 12, lineHeight: 18, color: '#BCD2C6', marginBottom: 4 },
  heroAmount: { ...typography.title, fontSize: 34, lineHeight: 43, color: '#F5F5EA', fontVariant: ['tabular-nums'] },
  amountNegative: { color: '#E0A295' },
  monthPill: { borderRadius: 13, backgroundColor: '#164B43', paddingVertical: 6, paddingHorizontal: 9 },
  monthPillText: { fontSize: 11, lineHeight: 16, color: '#DDE9DC' },
  chartNote: { fontSize: 11, lineHeight: 17, color: '#ABC6B8' },
  runwayBarsContainer: { flexGrow: 1, flexDirection: 'row', justifyContent: 'space-between', paddingTop: 10, paddingBottom: 2 },
  barColumn: { flex: 1, minWidth: 44, alignItems: 'center', paddingHorizontal: 3 },
  barTrack: { width: 15, height: 78, borderRadius: 8, backgroundColor: '#19464A', overflow: 'hidden', marginBottom: 6, borderTopWidth: 3, borderBottomWidth: 3, borderColor: 'transparent' },
  trackSelected: { backgroundColor: '#2E5F58' },
  zeroLine: { position: 'absolute', left: 0, right: 0, height: 1, backgroundColor: '#A2BAAF' },
  zeroDot: { position: 'absolute', width: 6, height: 6, borderRadius: 3, alignSelf: 'center', backgroundColor: '#B4D1C0' },
  barFill: { position: 'absolute', left: 0, right: 0, borderRadius: 6 },
  monthBarLabel: { fontSize: 11, lineHeight: 16, color: '#A5C1B5' },
  monthBarLabelSelected: { color: '#F4F7EA' },
  barYear: { fontSize: 9, lineHeight: 13, color: '#87A99B' },
  scaleLabel: { fontSize: 10, lineHeight: 15, color: '#9DBBAC', marginVertical: 8 },
  equationGrid: { flexDirection: 'row', backgroundColor: '#0A3D3D', borderRadius: 14, paddingVertical: 12, paddingHorizontal: 7, borderWidth: 1, borderColor: '#235249' },
  equationItem: { flex: 1, minWidth: 0, paddingHorizontal: 4 },
  metricHeading: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 },
  equationLabel: { fontSize: 10, lineHeight: 15, color: '#B8CDC2', flexShrink: 1 },
  equationValueSuccess: { fontSize: 12, lineHeight: 18, color: '#DBEFE0', fontVariant: ['tabular-nums'] },
  equationValue: { fontSize: 12, lineHeight: 18, color: '#ECF2E7', fontVariant: ['tabular-nums'] },
  equationDivider: { width: 1, backgroundColor: '#315F53', marginHorizontal: 3 },
  profilePromptBanner: { flexDirection: 'row', gap: 12, marginHorizontal: 18, marginBottom: 20, padding: 15, borderRadius: 18, backgroundColor: '#E8F0E5' },
  promptIconWrap: { width: 35, height: 35, borderRadius: 12, backgroundColor: '#D5E7D9', alignItems: 'center', justifyContent: 'center' },
  promptTextCol: { flex: 1 },
  promptTitle: { ...typography.title, fontSize: 16, lineHeight: 22, color: '#325B4B' },
  promptDesc: { fontSize: 12, lineHeight: 18, color: '#6A8275', marginTop: 4 },
  profileLink: { fontSize: 13, lineHeight: 20, color: '#2C6B53', marginTop: 7 },
  warningBanner: { flexDirection: 'row', marginHorizontal: 18, marginBottom: 18, padding: 13, borderRadius: 13, backgroundColor: '#F3E6DC', gap: 10 },
  warningIconWrap: { paddingTop: 2 },
  warningContent: { flex: 1 },
  warningTitle: { ...typography.title, fontSize: 14, lineHeight: 20, color: '#905C49' },
  warningDesc: { fontSize: 12, lineHeight: 18, color: '#966956' },
  timelineSection: { paddingHorizontal: 18 },
  timelineSectionTitle: { ...typography.title, fontSize: 19, lineHeight: 26, color: '#244440', marginBottom: 14 },
  timelineList: { paddingLeft: 0 },
  timelineItem: { flexDirection: 'row' },
  timelineLeft: { width: 18, alignItems: 'center', marginRight: 8 },
  timelineDot: { width: 9, height: 9, borderRadius: 5, marginTop: 18 },
  dotSuccess: { backgroundColor: '#43957C' },
  dotDanger: { backgroundColor: '#BA7766' },
  dotNeutral: { backgroundColor: '#98AA9C' },
  timelineLine: { width: 1, flex: 1, backgroundColor: '#B6CDBD', marginTop: 4 },
  timelineCard: { flex: 1, minWidth: 0, backgroundColor: '#FCFBF7', padding: 13, borderRadius: 15, borderWidth: 1, borderColor: '#E8EBE1', marginBottom: 10 },
  timelineSelected: { borderColor: '#B7CCB9' },
  timelineHeader: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 7, marginBottom: 4 },
  timelineMonth: { fontSize: 14, lineHeight: 21, color: '#2C4742' },
  timelineBufferValue: { fontSize: 14, lineHeight: 21, color: '#254E42', fontVariant: ['tabular-nums'], flexShrink: 1 },
  timelineBufferDanger: { color: '#A25B47' },
  timelineSubRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 7 },
  timelineMeta: { fontSize: 11, lineHeight: 17, color: '#7C8D83', flexShrink: 1, fontVariant: ['tabular-nums'] },
  timelineStatus: { fontSize: 10, lineHeight: 16, color: '#47624E', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 9 },
  pillSuccess: { backgroundColor: '#DDEEE0' },
  pillDanger: { backgroundColor: '#F0DED4' },
  pillNeutral: { backgroundColor: '#E8EADD' },
  retryButton: { margin: 18 },
  bottomSpacer: { height: 16 },
});