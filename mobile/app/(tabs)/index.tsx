import { t, formatCount } from '@/i18n';
import React, { useEffect, useRef } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Animated,
  Easing,

} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/dashboard';
import { ApiErrorDetail } from '@/types/api';
import { DashboardSummaryResponse } from '@/types/dashboard';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Icon, IconName } from '@/components/common/Icon';
import { Logo } from '@/components/common/Logo';
import Svg, { Defs, LinearGradient, RadialGradient, Stop, Rect, Path } from 'react-native-svg';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Button } from '@/components/common/Button';
import { colors, typography } from '@/constants/theme';
import { formatCurrency } from '@/utils/format';





const canvas = '#F6F4EF';

function getFirstName(fullName?: string | null): string | null {
  if (!fullName) return null;
  const trimmed = fullName.trim();
  if (!trimmed) return null;
  const first = trimmed.split(/\s+/)[0];
  if (!first) return null;
  return first.charAt(0).toUpperCase() + first.slice(1);
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return t("Good morning");
  if (h < 18) return t("Good afternoon");
  return t("Good evening");
}

function toNum(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === '') return 0;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return isNaN(n) ? 0 : n;
}



interface QuickActionItem {
  title: string;
  icon: IconName;
  route: '/forecast' | '/affordability' | '/(tabs)/obligations' | '/chat';
}

// Decorative artwork stays behind the content and never captures touches.
function FlowBackdrop() {
  return (
    <View pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
      <Svg width="100%" height="100%" viewBox="0 0 390 470" preserveAspectRatio="xMidYMid slice">
        <Defs>
          <RadialGradient id="glow" cx="85%" cy="40%" rx="85%" ry="65%">
            <Stop offset="0" stopColor="#377F6E" stopOpacity="0.6" />
            <Stop offset="1" stopColor="#02262D" stopOpacity="0" />
          </RadialGradient>
          <LinearGradient id="ribbon" x1="0%" y1="100%" x2="85%" y2="0%">
            <Stop offset="0" stopColor="#74AC96" stopOpacity="0.08" />
            <Stop offset="0.65" stopColor="#9DBCA5" stopOpacity="0.4" />
            <Stop offset="1" stopColor="#DBE1BB" stopOpacity="0.65" />
          </LinearGradient>
          <LinearGradient id="fold" x1="10%" y1="80%" x2="90%" y2="15%">
            <Stop offset="0" stopColor="#123F3D" stopOpacity="0.1" />
            <Stop offset="0.65" stopColor="#497E6B" stopOpacity="0.65" />
            <Stop offset="1" stopColor="#031F26" />
          </LinearGradient>
        </Defs>
        <Rect width="390" height="470" fill="url(#glow)" />
        <Path d="M-40 362 C50 237 112 332 199 238 S330 68 363 147 S420 221 432 163 L440 267 C371 269 360 157 325 185 S224 301 156 307 S39 299 -40 418Z" fill="url(#ribbon)" />
        <Path d="M-40 362 C50 237 112 332 199 238 S330 68 363 147 S420 221 432 163" fill="none" stroke="#D4DDBB" strokeOpacity="0.5" strokeWidth="0.8" />
        <Path d="M-32 396 C71 254 137 338 218 244 S331 165 367 227 S404 289 429 244 L430 353 C357 337 355 226 306 242 S178 358 111 337 S24 374 -32 443Z" fill="url(#fold)" />
        <Path d="M-32 396 C71 254 137 338 218 244 S331 165 367 227 S404 289 429 244" fill="none" stroke="#B7D5BD" strokeOpacity="0.35" strokeWidth="0.8" />
        <Path d="M-30 425 C61 345 111 387 207 294 S317 217 351 273 S406 379 430 340 L430 470 H-30Z" fill="#012C2D" fillOpacity="0.72" />
        <Path d="M-30 425 C61 345 111 387 207 294 S317 217 351 273 S406 379 430 340" fill="none" stroke="#B2CBA8" strokeOpacity="0.3" />
      </Svg>
    </View>
  );
}

export default function DashboardScreen() {
  const router = useRouter();
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';
  const firstName = getFirstName(user?.name);
  const userInitial = user?.name ? user.name.trim().charAt(0).toUpperCase() : 'D';

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

  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(12)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 400,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 400,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start();
  }, [fadeAnim, slideAnim]);

  if (isLoading && !isRefetching) {
    return (
      <ScreenWrapper backgroundColor={canvas}>
        <View style={styles.stateHeader}><Logo variant="symbol" tone="dark" width={28} /></View>
        <LoadingIndicator message={t("Loading your finances...")} />
      </ScreenWrapper>
    );
  }

  if (isError) {
    return (
      <ScreenWrapper scrollable backgroundColor={canvas}>
        <View style={styles.stateHeader}><Logo variant="symbol" tone="dark" width={28} /></View>
        <ErrorBanner message={error?.message || t("Unable to sync dashboard. Please check your connection.")} />
        <Button title={t("Try Again")} onPress={() => refetch()} style={styles.retryBtn} />
      </ScreenWrapper>
    );
  }

  const income = toNum(summary?.monthly_income);
  const fixed = toNum(summary?.fixed_expenses);
  const obligations = toNum(summary?.current_month_obligation_payments);
  const buffer = toNum(summary?.current_month_projected_buffer);
  const isNegative = summary?.has_current_month_negative_buffer ?? buffer < 0;
  const activeCount = summary?.active_obligations_count ?? 0;
  const hasIncome = income > 0;
  const hasProfile = hasIncome || fixed > 0;
  const capabilities: QuickActionItem[] = [
    { title: t("Cashflow\nForecast"), icon: 'trending-up', route: '/forecast' },
    { title: t("Affordability\nTest"), icon: 'pie-chart', route: '/affordability' },
    { title: t("Obligations\nLedger"), icon: 'credit-card', route: '/(tabs)/obligations' },
    { title: t("Ask\nDabbarha"), icon: 'message-circle', route: '/chat' },
  ];
  const metrics: { label: string; icon: IconName; value: string }[] = [
    { label: t("Income"), icon: 'arrow-up', value: hasProfile ? formatCurrency(income, currency) : t("Not set") },
    { label: t("Fixed Expenses"), icon: 'file-text', value: hasProfile ? formatCurrency(fixed, currency) : t("Not set") },
    { label: t("Obligations"), icon: 'credit-card', value: formatCurrency(obligations, currency) },
  ];

  return (
    <ScreenWrapper backgroundColor={colors.primary} statusBarStyle="light">
      <ScrollView
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContainer}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#C5DDD4" colors={[colors.primary]} />}
      >
        <Animated.View style={[styles.page, { opacity: fadeAnim, transform: [{ translateY: slideAnim }] }]}>
          <View style={styles.heroBackdrop}>
            <FlowBackdrop />
            <View style={styles.brandRow}>
              <View style={styles.brandLockup}>
                <Logo variant="symbol" tone="light" width={44} />
              </View>
              <TouchableOpacity onPress={() => router.push('/(tabs)/profile')} style={styles.avatarButton} accessibilityRole="button" accessibilityLabel={t("Open profile")} activeOpacity={0.7}>
                <Typography style={styles.avatarText}>{userInitial || 'D'}</Typography>
              </TouchableOpacity>
            </View>
            <View style={styles.greetingBlock}>
              <Typography style={styles.greetingLine}>{getGreeting()},</Typography>
              <Typography style={styles.greetingName} numberOfLines={2} adjustsFontSizeToFit minimumFontScale={0.65}>
                {firstName || t("Welcome")}.
              </Typography>
            </View>
          </View>

          <View style={styles.lowerSection}>
            <View style={styles.financialCard}>
              <TouchableOpacity
                activeOpacity={0.85}
                onPress={() => router.push(hasProfile ? '/forecast' : '/(tabs)/profile')}
                accessibilityRole="button"
                accessibilityLabel={hasProfile ? t('Monthly cash surplus {amount}. Open forecast', { amount: formatCurrency(buffer, currency) }) : t("Financial profile not set. Open profile to add income")}
                style={styles.financialMain}
              >
                <View style={styles.financialCopy}>
                  <Typography style={styles.financialLabel}>{t("Monthly Cash Surplus")}</Typography>
                  {hasProfile ? (
                    <Typography style={[styles.amount, isNegative && styles.negativeAmount]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.4}>
                      {formatCurrency(buffer, currency, { showSymbol: false })}
                      <Typography style={[styles.currency, isNegative && styles.negativeAmount]}> {currency}</Typography>
                    </Typography>
                  ) : (
                    <Typography style={styles.emptyTitle}>{t("Financial profile not set")}</Typography>
                  )}
                  <Typography style={styles.amountCaption}>
                    {!hasProfile ? t("Add income to unlock insights") : isNegative ? t("Commitments exceed income this month") : t("Available after your monthly commitments")}
                  </Typography>
                </View>
                <View style={styles.heroArrow}><Icon name="chevron-right" size={21} color="#E2EDE5" strokeWidth={1.5} /></View>
              </TouchableOpacity>
              <View style={styles.summaryStrip}>
                {metrics.map((metric, index) => (
                  <View key={metric.label} style={[styles.metric, index > 0 && styles.metricDivider]}>
                    <View style={styles.metricHeading}>
                      <Icon name={metric.icon} size={13} color="#517D74" strokeWidth={1.5} />
                      <Typography style={styles.metricLabel}>{metric.label}</Typography>
                    </View>
                    <Typography style={styles.metricValue} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.55} accessibilityLabel={`${metric.label}: ${metric.value}`}>
                      {metric.value}
                    </Typography>
                  </View>
                ))}
              </View>
            </View>

            <View style={styles.actions}>
              {capabilities.map((action) => (
                <TouchableOpacity key={action.route} style={styles.action} activeOpacity={0.7} onPress={() => router.push(action.route)} accessibilityRole="button" accessibilityLabel={action.title.replace('\n', ' ')}>
                  <View style={styles.actionIcon}><Icon name={action.icon} size={23} color={colors.primary} strokeWidth={1.6} /></View>
                  <Typography style={styles.actionLabel}>{action.title}</Typography>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              activeOpacity={0.8}
              onPress={() => router.push(!hasProfile ? '/(tabs)/profile' : '/forecast')}
              accessibilityRole="button"
              style={styles.insightCard}
            >
              <View style={[styles.insightIcon, hasProfile && isNegative && styles.warningIcon]}>
                <Icon name={!hasProfile ? 'wallet' : isNegative ? 'alert-triangle' : 'trending-up'} size={22} color={hasProfile && isNegative ? '#99583E' : '#217E6E'} strokeWidth={1.6} />
              </View>
              <View style={styles.insightCopy}>
                <Typography style={styles.insightTitle}>{!hasProfile ? t("Complete your setup") : isNegative ? t("Review your monthly shortfall") : t("Your month at a glance")}</Typography>
                <Typography style={styles.insightBody}>
                  {!hasProfile
                    ? t("Set your income and fixed expenses to see your full financial picture.")
                    : isNegative
                      ? t('Commitments exceed income by {amount} this month.', { amount: formatCurrency(Math.abs(buffer), currency) })
                      : t(activeCount === 1 ? '{count} active obligation. Explore your projected cashflow.' : '{count} active obligations. Explore your projected cashflow.', { count: formatCount(activeCount) })}
                </Typography>
              </View>
              <Icon name="chevron-right" size={18} color="#54716F" strokeWidth={1.5} />
            </TouchableOpacity>
          </View>
        </Animated.View>
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  scroll: { backgroundColor: canvas },
  scrollContainer: { flexGrow: 1 },
  page: { flexGrow: 1, backgroundColor: canvas },
  heroBackdrop: { backgroundColor: '#02262D', paddingHorizontal: 20, paddingTop: 14, paddingBottom: 125, overflow: 'hidden' },
  brandRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brandLockup: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  brandWordmark: { fontFamily: typography.fontFamily, fontSize: 25, lineHeight: 32, letterSpacing: -0.6, color: '#F6F4EF' },
  avatarButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#2B655E', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#487D72' },
  avatarText: { color: '#E6F0E9', fontSize: 17, fontWeight: '400' },
  greetingBlock: { marginTop: 34, paddingBottom: 26 },
  greetingLine: { fontFamily: typography.fontFamily, fontSize: 25, lineHeight: 32, color: '#BED0C7', letterSpacing: -0.4 },
  greetingName: { fontFamily: typography.fontFamily, fontSize: 54, lineHeight: 61, fontWeight: typography.title.fontWeight, color: '#F9F8F0', letterSpacing: typography.title.letterSpacing },
  lowerSection: { paddingHorizontal: 16, paddingBottom: 28, flexGrow: 1 },
  financialCard: { marginTop: -86, borderRadius: 27, backgroundColor: '#073D3D', borderWidth: 1, borderColor: 'rgba(177,209,189,0.34)', shadowColor: '#001B20', shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.15, shadowRadius: 20, elevation: 5 },
  financialMain: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingTop: 23, paddingBottom: 22, minHeight: 150, gap: 10 },
  financialCopy: { flex: 1, minWidth: 0 },
  financialLabel: { fontSize: 14, lineHeight: 20, color: '#CADBD3', marginBottom: 5 },
  amount: { fontFamily: typography.fontFamily, fontSize: 46, lineHeight: 55, color: '#FAF8F0', fontWeight: typography.title.fontWeight, letterSpacing: -1.4, fontVariant: ['tabular-nums'] },
  currency: { fontFamily: typography.fontFamily, fontSize: 24, lineHeight: 32, color: '#FAF8F0', fontWeight: typography.title.fontWeight, letterSpacing: -0.3 },
  negativeAmount: { color: '#F4B9A6' },
  emptyTitle: { fontFamily: typography.fontFamily, fontSize: 30, lineHeight: 36, color: '#F9F8F0', letterSpacing: -0.6, marginVertical: 3 },
  amountCaption: { fontSize: 12, lineHeight: 18, color: '#B4CCC3', marginTop: 3 },
  heroArrow: { width: 42, height: 42, borderRadius: 21, backgroundColor: '#2C6059', alignItems: 'center', justifyContent: 'center' },
  summaryStrip: { flexDirection: 'row', backgroundColor: '#EFF0E9', borderRadius: 23, borderWidth: 4, borderColor: '#FCFCF7', paddingVertical: 15, paddingHorizontal: 4 },
  metric: { flex: 1, minWidth: 0, paddingHorizontal: 7, justifyContent: 'center' },
  metricDivider: { borderStartWidth: StyleSheet.hairlineWidth, borderStartColor: '#CFD9D1' },
  metricHeading: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 3 },
  metricLabel: { fontSize: 10, lineHeight: 14, color: '#516864', flexShrink: 1 },
  metricValue: { fontSize: 12, lineHeight: 18, fontWeight: '600', color: '#173B3C', fontVariant: ['tabular-nums'] },
  actions: { flexDirection: 'row', gap: 9, marginTop: 25 },
  action: { flex: 1, minWidth: 0, alignItems: 'center', backgroundColor: '#F4F3EF', borderRadius: 19, paddingHorizontal: 3, paddingTop: 12, paddingBottom: 15, borderWidth: 1, borderColor: '#E9EAE4' },
  actionIcon: { width: 39, height: 39, borderRadius: 14, backgroundColor: '#EBEEE8', alignItems: 'center', justifyContent: 'center', marginBottom: 9 },
  actionLabel: { fontSize: 11, lineHeight: 16, textAlign: 'center', color: '#213C40', fontWeight: '500' },
  insightCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 17, marginTop: 22, borderRadius: 23, borderWidth: 1, borderColor: '#E9EAE4', backgroundColor: '#FAF9F5' },
  insightIcon: { width: 46, height: 46, borderRadius: 15, backgroundColor: '#DCEFE6', alignItems: 'center', justifyContent: 'center' },
  warningIcon: { backgroundColor: '#F7E8DE' },
  insightCopy: { flex: 1, minWidth: 0 },
  insightTitle: { fontSize: 14, lineHeight: 20, fontWeight: '600', color: '#253C40' },
  insightBody: { fontSize: 12, lineHeight: 18, color: '#6F7F80', marginTop: 3 },
  stateHeader: { padding: 20 },
  retryBtn: { marginTop: 16 },
});
