import { t, statusLabel, categoryLabel, monthCount, formatCount } from '@/i18n';
import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { ObligationResponse, ObligationStatus } from '@/types/obligation';
import { Typography } from '@/components/common/Typography';
import { Badge, BadgeVariant } from '@/components/common/Badge';
import { Icon, IconName } from '@/components/common/Icon';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { formatCurrency } from '@/utils/format';

interface ObligationCardProps {
  obligation: ObligationResponse;
  currency: string;
  onPress: (obligation: ObligationResponse) => void;
}

const statusBadgeVariant: Record<ObligationStatus, BadgeVariant> = {
  active: 'success',
  completed: 'info',
  late: 'warning',
  defaulted: 'error',
};

const CATEGORY_ICON: Record<string, IconName> = {
  Electronics: 'credit-card',
  Vehicle: 'trending-up',
  Housing: 'home',
  Education: 'list-checks',
  Personal: 'user',
  default: 'file-text',
};

function pickCategoryIcon(category: string): IconName {
  return CATEGORY_ICON[category] ?? CATEGORY_ICON.default;
}

export function ObligationCard({ obligation, currency, onPress }: ObligationCardProps) {
  const badgeVariant =
    statusBadgeVariant[obligation.status as ObligationStatus] || 'neutral';

  return (
    <TouchableOpacity
      activeOpacity={0.75}
      onPress={() => onPress(obligation)}
      style={styles.cardContainer}
    >
      <View style={styles.topRow}>
        <View style={styles.iconBadge}>
          <Icon
            name={pickCategoryIcon(obligation.category)}
            size={18}
            color={colors.primary}
          />
        </View>

        <View style={styles.titleCol}>
          <Typography style={styles.itemName} numberOfLines={1}>
            {obligation.item_name}
          </Typography>
          <Typography variant="caption" color={colors.textSecondary} numberOfLines={1}>
            {obligation.provider} · {categoryLabel(obligation.category)}
          </Typography>
        </View>

        <Badge label={statusLabel(obligation.status)} variant={badgeVariant} />
      </View>

      <View style={styles.divider} />

      <View style={styles.financialRow}>
        <View style={styles.amountCol}>
          <Typography variant="caption" style={styles.metaLabel}>
            {t("MONTHLY INSTALLMENT")}</Typography>
          <Typography style={styles.installmentValue} numberOfLines={1}>
            {formatCurrency(obligation.monthly_installment_amount, currency)}
            <Typography variant="caption" color={colors.textSecondary}>
              {' '}{t("/mo")}</Typography>
          </Typography>
        </View>

        <View style={styles.amountColRight}>
          <Typography variant="caption" style={styles.metaLabel}>
            {t("TOTAL VALUE")}</Typography>
          <Typography style={styles.totalValue} numberOfLines={1}>
            {formatCurrency(obligation.total_amount, currency)}
          </Typography>
        </View>
      </View>

      <View style={styles.scheduleRow}>
        <View style={styles.schedulePill}>
          <Icon name="calendar" size={12} color="#0D9488" />
          <Typography style={styles.scheduleText}>
            {t('Due on day {day}', { day: formatCount(obligation.due_day_of_month) })}
          </Typography>
        </View>

        <View style={styles.schedulePill}>
          <Icon name="clock" size={12} color={colors.textMuted} />
          <Typography style={styles.scheduleText}>
            {monthCount(obligation.term_months)}
          </Typography>
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  cardContainer: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconBadge: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: '#F0FDFA',
    borderWidth: 1,
    borderColor: '#CCFBF1',
    alignItems: 'center',
    justifyContent: 'center',
    marginEnd: spacing.sm + 2,
  },
  titleCol: {
    flex: 1,
    marginEnd: spacing.sm,
  },
  itemName: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 1,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.sm + 2,
  },
  financialRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.sm + 2,
  },
  amountCol: {
    flex: 1,
  },
  amountColRight: {
    alignItems: 'flex-end',
  },
  metaLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.6,
    color: colors.textMuted,
    marginBottom: 2,
  },
  installmentValue: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.primary,
    fontVariant: ['tabular-nums'],
  },
  totalValue: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.textSecondary,
    fontVariant: ['tabular-nums'],
  },
  scheduleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  schedulePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    gap: 4,
  },
  scheduleText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.textSecondary,
  },
});
