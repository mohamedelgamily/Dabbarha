import React, { useEffect, useMemo, useRef } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Pressable,
  Animated,
  Easing,
  Dimensions,
} from 'react-native';
import Svg, {
  Circle,
  Defs,
  LinearGradient,
  Path,
  Stop,
  G,
} from 'react-native-svg';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/dashboard';
import { ApiErrorDetail } from '@/types/api';
import { DashboardSummaryResponse } from '@/types/dashboard';
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Icon, IconName } from '@/components/common/Icon';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Button } from '@/components/common/Button';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { formatCurrency } from '@/utils/format';

const SCREEN_W = Dimensions.get('window').width;
const HERO_W = SCREEN_W - spacing.lg * 2;
const HERO_H = 360;
const RAIL_X = 56;
const MAX_NODE = 44;
const MIN_NODE = 14;

function getFirstName(fullName?: string | null): string | null {
  if (!fullName) return null;
  const trimmed = fullName.trim();
  if (!trimmed) return null;
  const first = trimmed.split(/\s+/)[0];
  return first.charAt(0).toUpperCase() + first.slice(1);
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

function toNum(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === '') return 0;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return isNaN(n) ? 0 : n;
}

function formatCompact(value: number): string {
  if (!isFinite(value)) return '0';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toFixed(0);
}

interface FlowNode {
  key: string;
  label: string;
  value: number;
  icon: IconName;
  tone: 'income' | 'expense' | 'obligation' | 'buffer';
  isDelta?: boolean;
}

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  style: any;
  formatter: (n: number) => string;
}

function AnimatedCounter({ value, duration = 700, style, formatter }: AnimatedCounterProps) {
  const anim = useRef(new Animated.Value(0)).current;
  const displayRef = useRef<Animated.AnimatedInterpolation<number> | Animated.Value>(anim);
  const [shown, setShown] = React.useState(formatter(0));

  useEffect(() => {
    anim.setValue(0);
    const id = anim.addListener(({ value: v }) => {
      setShown(formatter(v));
    });
    Animated.timing(anim, {
      toValue: value,
      duration,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
    return () => {
      anim.removeListener(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  displayRef.current = anim;
  void displayRef;
  return <Animated.Text style={style}>{shown}</Animated.Text>;
}

interface HeroCanvasProps {
  nodes: FlowNode[];
  isNegative: boolean;
  ratio: number;
}

function HeroCanvas({ nodes, isNegative, ratio }: HeroCanvasProps) {
  const maxValue = useMemo(() => {
    const positives = nodes
      .map((n) => (n.tone === 'buffer' ? 0 : Math.abs(n.value)))
      .filter((v) => v > 0);
    return Math.max(...positives, 1);
  }, [nodes]);

  const nodePositions = useMemo(() => {
    const topPad = 64;
    const bottomPad = 64;
    const usableH = HERO_H - topPad - bottomPad;
    const step = usableH / Math.max(1, nodes.length - 1);
    return nodes.map((n, i) => {
      const proportion = maxValue > 0 ? Math.min(1, Math.abs(n.value) / maxValue) : 0;
      const radius = n.tone === 'buffer'
        ? isNegative
          ? MIN_NODE + 6
          : MIN_NODE + 14
        : MIN_NODE + proportion * (MAX_NODE - MIN_NODE);
      return {
        cy: topPad + step * i,
        r: radius,
        node: n,
      };
    });
  }, [nodes, maxValue, isNegative]);

  const pathD = useMemo(() => {
    if (nodePositions.length < 2) return '';
    const pts = nodePositions.map((p) => ({ x: RAIL_X, y: p.cy }));
    const start = pts[0];
    let d = `M ${start.x} ${start.y}`;
    for (let i = 1; i < pts.length; i++) {
      const prev = pts[i - 1];
      const cur = pts[i];
      const midY = (prev.y + cur.y) / 2;
      d += ` C ${prev.x} ${midY}, ${cur.x} ${midY}, ${cur.x} ${cur.y}`;
    }
    return d;
  }, [nodePositions]);

  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!isNegative) {
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1600,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 1600,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [isNegative, pulse]);

  const bufferRingScale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 1.35],
  });
  const bufferRingOpacity = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [0.45, 0],
  });

  return (
    <View style={styles.heroCanvas}>
      <Svg
        width={HERO_W}
        height={HERO_H}
        viewBox={`0 0 ${HERO_W} ${HERO_H}`}
        style={StyleSheet.absoluteFill}
      >
        <Defs>
          <LinearGradient id="flowGrad" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#5B8E96" stopOpacity="0.32" />
            <Stop offset="1" stopColor="#5B8E96" stopOpacity="0" />
          </LinearGradient>
          <LinearGradient id="arcGrad" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#0E4A56" stopOpacity="0.55" />
            <Stop offset="1" stopColor="#02262D" stopOpacity="0" />
          </LinearGradient>
        </Defs>

        <G opacity={0.85}>
          <Path
            d={`M ${HERO_W * 0.65} -40 Q ${HERO_W * 1.15} ${HERO_H * 0.25}, ${HERO_W * 0.55} ${HERO_H * 0.55} T ${HERO_W * 0.2} ${HERO_H + 40}`}
            stroke="url(#arcGrad)"
            strokeWidth={120}
            fill="none"
          />
        </G>

        <G opacity={0.55}>
          <Path
            d={`M -40 ${HERO_H * 0.7} Q ${HERO_W * 0.3} ${HERO_H * 0.55}, ${HERO_W * 0.75} ${HERO_H * 0.85} T ${HERO_W + 40} ${HERO_H * 1.05}`}
            stroke="url(#arcGrad)"
            strokeWidth={90}
            fill="none"
          />
        </G>

        <Path
          d={pathD}
          stroke="url(#flowGrad)"
          strokeWidth={1.5}
          fill="none"
        />

        {nodePositions.map((p, idx) => {
          const isBuffer = p.node.tone === 'buffer';
          const fill = isBuffer
            ? isNegative
              ? '#FCA5A5'
              : '#FFFFFF'
            : '#02262D';
          const stroke = isBuffer
            ? isNegative
              ? '#FCA5A5'
              : '#FFFFFF'
            : '#5B8E96';
          return (
            <G key={p.node.key}>
              {isBuffer && isNegative ? (
                <AnimatedCircle
                  cx={RAIL_X}
                  cy={p.cy}
                  r={p.r + 8}
                  fill="none"
                  stroke="#FCA5A5"
                  strokeWidth={1}
                  opacity={bufferRingOpacity}
                  scale={bufferRingScale}
                />
              ) : null}
              <Circle
                cx={RAIL_X}
                cy={p.cy}
                r={p.r}
                fill={fill}
                stroke={stroke}
                strokeWidth={1.25}
                opacity={isBuffer ? 1 : 0.95}
              />
              {!isBuffer ? (
                <Circle
                  cx={RAIL_X}
                  cy={p.cy}
                  r={Math.max(2, p.r * 0.35)}
                  fill="#5B8E96"
                  opacity={0.6}
                />
              ) : null}
              {idx === 0 ? null : null}
            </G>
          );
        })}
      </Svg>

      {nodePositions.map((p) => {
        const left = p.r + spacing.md;
        return (
          <View
            key={`label-${p.node.key}`}
            style={[
              styles.nodeLabel,
              { top: p.cy - 14, left: RAIL_X + left },
            ]}
          >
            <Typography
              variant="caption"
              style={styles.nodeLabelText}
              color="rgba(255,255,255,0.62)"
            >
              {p.node.label}
            </Typography>
          </View>
        );
      })}

      {nodePositions.map((p) => {
        const rightX = RAIL_X - p.r - spacing.md;
        return (
          <View
            key={`value-${p.node.key}`}
            style={[
              styles.nodeValue,
              { top: p.cy - 10, right: HERO_W - rightX },
            ]}
          >
            <Typography
              variant="bodyBold"
              style={styles.nodeValueText}
              color={p.node.tone === 'buffer' && isNegative ? '#FCA5A5' : 'rgba(255,255,255,0.92)'}
            >
              {p.node.tone === 'buffer' && isNegative ? '−' : ''}
              {formatCompact(p.node.value)}
            </Typography>
          </View>
        );
      })}

      {ratio > 0 ? (
        <View style={styles.ratioBadge}>
          <View style={styles.ratioBadgeInner}>
            <Typography
              variant="caption"
              color="rgba(255,255,255,0.78)"
              style={styles.ratioLabel}
            >
              Committed
            </Typography>
            <Typography
              variant="bodyBold"
              color="#FFFFFF"
              style={styles.ratioValue}
            >
              {Math.round(ratio * 100)}%
            </Typography>
            <View style={styles.ratioBarTrack}>
              <View
                style={[
                  styles.ratioBarFill,
                  {
                    width: `${Math.min(100, Math.max(0, ratio * 100))}%`,
                    backgroundColor: ratio > 1 ? '#FCA5A5' : '#5B8E96',
                  },
                ]}
              />
            </View>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

interface ActionTileProps {
  icon: IconName;
  title: string;
  caption: string;
  onPress: () => void;
}

function ActionTile({ icon, title, caption, onPress }: ActionTileProps) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionTile,
        pressed && styles.actionTilePressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={title}
    >
      <View style={styles.actionIconWrap}>
        <Icon name={icon} size={20} tone="primary" />
      </View>
      <View style={styles.actionTextCol}>
        <Typography variant="bodyBold" numberOfLines={1}>
          {title}
        </Typography>
        <Typography
          variant="caption"
          color={colors.textSecondary}
          numberOfLines={1}
        >
          {caption}
        </Typography>
      </View>
      <Icon name="chevron-right" size={18} tone="muted" />
    </Pressable>
  );
}

export default function DashboardScreen() {
  const router = useRouter();
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';
  const firstName = getFirstName(user?.name);

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

  const entry = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(entry, {
      toValue: 1,
      duration: 320,
      easing: Easing.out(Easing.quad),
      useNativeDriver: true,
    }).start();
  }, [entry]);
  const entryOpacity = entry;
  const entryTranslate = entry.interpolate({
    inputRange: [0, 1],
    outputRange: [12, 0],
  });

  if (isLoading && !isRefetching) {
    return (
      <ScreenWrapper>
        <View style={styles.headerArea}>
          <Typography variant="caption" color={colors.textMuted}>
            {getGreeting()}
            {firstName ? `, ${firstName}` : ''}
          </Typography>
          <Typography variant="h1" style={styles.headerTitle}>
            Your money, figured out.
          </Typography>
        </View>
        <LoadingIndicator message="Loading your finances..." />
      </ScreenWrapper>
    );
  }

  if (isError) {
    return (
      <ScreenWrapper scrollable>
        <View style={styles.headerArea}>
          <Typography variant="caption" color={colors.textMuted}>
            {getGreeting()}
            {firstName ? `, ${firstName}` : ''}
          </Typography>
          <Typography variant="h1" style={styles.headerTitle}>
            Your money, figured out.
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

  const income = toNum(summary?.monthly_income);
  const fixed = toNum(summary?.fixed_expenses);
  const obligations = toNum(summary?.current_month_obligation_payments);
  const buffer = toNum(summary?.current_month_projected_buffer);
  const isNegative = summary?.has_current_month_negative_buffer ?? buffer < 0;
  const ratio = income > 0 ? (fixed + obligations) / income : 0;

  const nodes: FlowNode[] = [
    { key: 'income', label: 'Income', value: income, icon: 'arrow-down', tone: 'income' },
    { key: 'fixed', label: 'Fixed', value: fixed, icon: 'home', tone: 'expense' },
    { key: 'obligations', label: 'Commitments', value: obligations, icon: 'list-checks', tone: 'obligation' },
    { key: 'buffer', label: isNegative ? 'Deficit' : 'Available', value: Math.abs(buffer), icon: 'wallet', tone: 'buffer' },
  ];

  const greeting = getGreeting();

  return (
    <ScreenWrapper>
      <ScrollView
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
        <Animated.View
          style={{
            opacity: entryOpacity,
            transform: [{ translateY: entryTranslate }],
          }}
        >
          <View style={styles.headerArea}>
            <View style={styles.headerRow}>
              <View style={styles.headerTextCol}>
                <Typography
                  variant="caption"
                  color={colors.textMuted}
                  style={styles.kicker}
                >
                  {greeting}
                  {firstName ? `, ${firstName}` : ''}
                </Typography>
                <Typography variant="h1" style={styles.headerTitle}>
                  Your money, figured out.
                </Typography>
                <Typography
                  variant="body"
                  color={colors.textSecondary}
                  style={styles.headerSub}
                >
                  Here's where your month stands.
                </Typography>
              </View>
              <View style={styles.logoMark}>
                <Icon name="trending-up" size={20} tone="primary" />
              </View>
            </View>
          </View>

          <View style={styles.heroSurface}>
            <HeroCanvas nodes={nodes} isNegative={isNegative} ratio={ratio} />

            <View style={styles.heroValueArea}>
              <Typography
                variant="caption"
                style={styles.heroLabel}
                color="rgba(255,255,255,0.62)"
              >
                {isNegative ? 'Projected buffer' : 'Available this month'}
              </Typography>
              <View style={styles.heroValueRow}>
                <AnimatedCounter
                  value={buffer}
                  formatter={(n) => formatCurrency(n.toFixed(2), currency)}
                  style={[
                    styles.heroValue,
                    { color: isNegative ? '#FCA5A5' : '#FFFFFF' },
                  ]}
                />
              </View>
              <View style={styles.heroSubRow}>
                <View style={styles.heroSubItem}>
                  <Typography
                    variant="caption"
                    style={styles.heroSubLabel}
                    color="rgba(255,255,255,0.5)"
                  >
                    Income
                  </Typography>
                  <Typography
                    variant="bodyBold"
                    style={styles.heroSubValue}
                    color="#FFFFFF"
                  >
                    {formatCurrency(income, currency)}
                  </Typography>
                </View>
                <View style={styles.heroSubDivider} />
                <View style={styles.heroSubItem}>
                  <Typography
                    variant="caption"
                    style={styles.heroSubLabel}
                    color="rgba(255,255,255,0.5)"
                  >
                    Committed
                  </Typography>
                  <Typography
                    variant="bodyBold"
                    style={styles.heroSubValue}
                    color="#FFFFFF"
                  >
                    {formatCurrency(fixed + obligations, currency)}
                  </Typography>
                </View>
              </View>
            </View>
          </View>

          {isNegative ? (
            <View style={styles.tensionRow}>
              <View style={styles.tensionDot} />
              <Typography
                variant="caption"
                color={colors.textSecondary}
                style={styles.tensionText}
              >
                Commitments exceed income this month. Review your obligations or check affordability.
              </Typography>
            </View>
          ) : ratio > 0.85 ? (
            <View style={styles.tensionRow}>
              <View style={[styles.tensionDot, { backgroundColor: colors.warning }]} />
              <Typography
                variant="caption"
                color={colors.textSecondary}
                style={styles.tensionText}
              >
                {Math.round(ratio * 100)}% of your income is already committed. Plan ahead with a forecast.
              </Typography>
            </View>
          ) : (
            <View style={styles.tensionRow}>
              <View style={[styles.tensionDot, { backgroundColor: colors.success }]} />
              <Typography
                variant="caption"
                color={colors.textSecondary}
                style={styles.tensionText}
              >
                Healthy margin. {Math.round((1 - ratio) * 100)}% of income is uncommitted.
              </Typography>
            </View>
          )}

          <View style={styles.sectionHead}>
            <Typography variant="h3">Plan your next move</Typography>
            <Typography
              variant="caption"
              color={colors.textSecondary}
              style={styles.sectionHint}
            >
              Tap a tool to explore your finances
            </Typography>
          </View>

          <View style={styles.tilesRow}>
            <ActionTile
              icon="trending-up"
              title="Forecast"
              caption="Project buffer"
              onPress={() => router.push('/forecast' as any)}
            />
            <ActionTile
              icon="pie-chart"
              title="Affordability"
              caption="Test a commitment"
              onPress={() => router.push('/affordability' as any)}
            />
            <ActionTile
              icon="message-circle"
              title="Ask"
              caption="Chat with Dabbarha"
              onPress={() => router.push('/chat' as any)}
            />
          </View>

          <View style={styles.bottomSpacer} />
        </Animated.View>
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
  },
  headerArea: {
    marginTop: spacing.sm,
    marginBottom: spacing.lg,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  headerTextCol: {
    flex: 1,
    marginRight: spacing.md,
  },
  kicker: {
    marginBottom: spacing.xs,
    letterSpacing: 0.2,
  },
  headerTitle: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '700',
    letterSpacing: -0.4,
  },
  headerSub: {
    marginTop: spacing.xs,
    lineHeight: 22,
  },
  logoMark: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroSurface: {
    backgroundColor: colors.primary,
    borderRadius: 28,
    overflow: 'hidden',
    marginBottom: spacing.md,
  },
  heroCanvas: {
    width: HERO_W,
    height: HERO_H,
    position: 'relative',
  },
  nodeLabel: {
    position: 'absolute',
  },
  nodeLabelText: {
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  nodeValue: {
    position: 'absolute',
    alignItems: 'flex-end',
  },
  nodeValueText: {
    fontSize: 13,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  ratioBadge: {
    position: 'absolute',
    top: spacing.md,
    right: spacing.md,
  },
  ratioBadgeInner: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 2,
    minWidth: 92,
  },
  ratioLabel: {
    fontSize: 10,
    fontWeight: '500',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  ratioValue: {
    fontSize: 18,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
    marginTop: 2,
  },
  ratioBarTrack: {
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: 2,
    marginTop: spacing.xs,
    overflow: 'hidden',
  },
  ratioBarFill: {
    height: '100%',
    borderRadius: 2,
  },
  heroValueArea: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  heroLabel: {
    fontSize: 11,
    fontWeight: '500',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  heroValueRow: {
    marginTop: spacing.xs,
  },
  heroValue: {
    fontSize: 36,
    lineHeight: 42,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
    letterSpacing: -0.5,
  },
  heroSubRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.1)',
  },
  heroSubItem: {
    flex: 1,
  },
  heroSubDivider: {
    width: 1,
    alignSelf: 'stretch',
    backgroundColor: 'rgba(255,255,255,0.1)',
    marginHorizontal: spacing.md,
  },
  heroSubLabel: {
    fontSize: 11,
    fontWeight: '500',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  heroSubValue: {
    fontSize: 15,
    fontWeight: '600',
    marginTop: 2,
    fontVariant: ['tabular-nums'],
  },
  tensionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    marginBottom: spacing.lg,
    gap: spacing.sm,
  },
  tensionDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.error,
  },
  tensionText: {
    flex: 1,
    lineHeight: 18,
  },
  sectionHead: {
    marginBottom: spacing.sm,
  },
  sectionHint: {
    marginTop: 2,
  },
  tilesRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  actionTile: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    minHeight: 96,
    justifyContent: 'space-between',
  },
  actionTilePressed: {
    backgroundColor: colors.primaryMuted,
    borderColor: colors.primaryMuted,
  },
  actionIconWrap: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionTextCol: {
    marginTop: spacing.sm,
  },
  retryButton: {
    marginTop: spacing.md,
  },
  bottomSpacer: {
    height: spacing.xl,
  },
});
