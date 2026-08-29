import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { ObligationResponse, ObligationStatus } from '@/types/obligation';
import { Card } from '@/components/common/Card';
import { Typography } from '@/components/common/Typography';
import { Badge, BadgeVariant } from '@/components/common/Badge';
import { colors, spacing } from '@/constants/theme';

interface ObligationCardProps {
  obligation: ObligationResponse;
  onPress: (obligation: ObligationResponse) => void;
}

const statusBadgeVariant: Record<ObligationStatus, BadgeVariant> = {
  active: 'success',
  completed: 'info',
  late: 'warning',
  defaulted: 'error',
};

export function ObligationCard({ obligation, onPress }: ObligationCardProps) {
  const badgeVariant =
    statusBadgeVariant[obligation.status as ObligationStatus] || 'neutral';

  const formatCurrency = (amount: string | number) => {
    const num = Number(amount);
    if (isNaN(num)) return `${amount} EGP`;
    return `${num.toLocaleString()} EGP`;
  };

  return (
    <TouchableOpacity
      activeOpacity={0.7}
      onPress={() => onPress(obligation)}
      style={styles.touchable}
    >
      <Card style={styles.card}>
        <View style={styles.headerRow}>
          <View style={styles.titleContainer}>
            <Typography variant="h3" style={styles.itemName}>
              {obligation.item_name}
            </Typography>
            <Typography variant="caption" color={colors.textSecondary}>
              {obligation.provider} • {obligation.category}
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
              {formatCurrency(obligation.monthly_installment_amount)}/mo
            </Typography>
          </View>

          <View style={styles.detailCol}>
            <Typography variant="caption" color={colors.textMuted}>
              Total Amount
            </Typography>
            <Typography variant="body" style={styles.totalAmount}>
              {formatCurrency(obligation.total_amount)}
            </Typography>
          </View>
        </View>

        <View style={styles.footerRow}>
          <Typography variant="caption" color={colors.textSecondary}>
            Due Day: {obligation.due_day_of_month}th of every month
          </Typography>
          <Typography variant="caption" color={colors.textSecondary}>
            {obligation.term_months} months
          </Typography>
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
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  titleContainer: {
    flex: 1,
    marginRight: spacing.sm,
  },
  itemName: {
    marginBottom: spacing.xs / 2,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.sm + 2,
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
    paddingTop: spacing.xs,
  },
});
