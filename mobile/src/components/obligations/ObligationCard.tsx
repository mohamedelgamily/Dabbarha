import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { ObligationResponse, ObligationStatus } from '@/types/obligation';
import { Card } from '@/components/common/Card';
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
      activeOpacity={0.7}
      onPress={() => onPress(obligation)}
      style={styles.touchable}
    >
      <Card style={styles.card}>
        <View style={styles.headerRow}>
          <View style={styles.iconWrap}>
            <Icon name={pickCategoryIcon(obligation.category)} size={20} tone="primary" />
          </View>
          <View style={styles.titleContainer}>
            <Typography variant="h3" style={styles.itemName}>
              {obligation.item_name}
            </Typography>
            <Typography variant="caption" color={colors.textSecondary}>
              {obligation.provider} · {obligation.category}
            </Typography>
          </View>
          <Badge label={obligation.status} variant={badgeVariant} />
        </View>

        <View style={styles.divider} />

        <View style={styles.detailsRow}>
          <View style={styles.detailCol}>
            <Typography variant="caption" color={colors.textMuted}>
              Monthly Installment
            </Typography>
            <Typography variant="bodyBold" color={colors.primary}>
              {formatCurrency(obligation.monthly_installment_amount, currency)}/mo
            </Typography>
          </View>

          <View style={styles.detailCol}>
            <Typography variant="caption" color={colors.textMuted}>
              Total Amount
            </Typography>
            <Typography variant="body" style={styles.totalAmount}>
              {formatCurrency(obligation.total_amount, currency)}
            </Typography>
          </View>
        </View>

        <View style={styles.footerRow}>
          <View style={styles.footerItem}>
            <Icon name="calendar" size={14} tone="muted" />
            <Typography variant="caption" color={colors.textSecondary} style={styles.footerText}>
              Due on day {obligation.due_day_of_month}
            </Typography>
          </View>
          <View style={styles.footerItem}>
            <Icon name="clock" size={14} tone="muted" />
            <Typography variant="caption" color={colors.textSecondary} style={styles.footerText}>
              {obligation.term_months} months
            </Typography>
          </View>
        </View>
      </Card>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  touchable: {
    marginBottom: spacing.md,
  },
  card: {
    padding: spacing.md,
    borderRadius: borderRadius.xl,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  titleContainer: {
    flex: 1,
    marginRight: spacing.sm,
  },
  itemName: {
    marginBottom: 2,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.md,
  },
  detailsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  detailCol: {
    flex: 1,
  },
  totalAmount: {
    marginTop: 2,
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
  footerItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  footerText: {
    marginLeft: spacing.xs,
  },
});
