import React from 'react';
import {
  Modal,
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ObligationResponse, ObligationStatus } from '@/types/obligation';
import { Typography } from '@/components/common/Typography';
import { Badge, BadgeVariant } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Icon, IconName } from '@/components/common/Icon';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { formatCurrency, formatDate } from '@/utils/format';

interface ObligationDetailModalProps {
  visible: boolean;
  onClose: () => void;
  obligation: ObligationResponse | null;
  currency: string;
  onEdit: (obligation: ObligationResponse) => void;
  onDelete: (obligation: ObligationResponse) => void;
  isDeleting?: boolean;
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

export function ObligationDetailModal({
  visible,
  onClose,
  obligation,
  currency,
  onEdit,
  onDelete,
  isDeleting = false,
}: ObligationDetailModalProps) {
  if (!obligation) return null;

  const badgeVariant =
    statusBadgeVariant[obligation.status as ObligationStatus] || 'neutral';

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.modalContainer}>
        <View style={styles.header}>
          <Typography style={styles.headerTitle}>Obligation Details</Typography>
          <TouchableOpacity
            onPress={onClose}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            style={styles.closeButton}
            accessibilityRole="button"
            accessibilityLabel="Close"
          >
            <Icon name="x" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Main Financial Hero Box */}
          <View style={styles.heroBox}>
            <View style={styles.heroTop}>
              <View style={styles.heroIconBadge}>
                <Icon
                  name={pickCategoryIcon(obligation.category)}
                  size={22}
                  color="#2DD4BF"
                />
              </View>
              <View style={styles.heroTitleCol}>
                <Typography style={styles.heroItemName} numberOfLines={1}>
                  {obligation.item_name}
                </Typography>
                <Typography style={styles.heroProviderText}>
                  {obligation.provider} · {obligation.category}
                </Typography>
              </View>
              <Badge label={obligation.status} variant={badgeVariant} />
            </View>

            <View style={styles.heroDivider} />

            <View style={styles.heroAmountsGrid}>
              <View style={styles.amountCol}>
                <Typography style={styles.heroAmountLabel}>
                  MONTHLY INSTALLMENT
                </Typography>
                <Typography style={styles.heroInstallmentAmount}>
                  {formatCurrency(obligation.monthly_installment_amount, currency)}
                </Typography>
              </View>

              <View style={styles.amountColRight}>
                <Typography style={styles.heroAmountLabel}>
                  TOTAL COMMITMENT
                </Typography>
                <Typography style={styles.heroTotalAmount}>
                  {formatCurrency(obligation.total_amount, currency)}
                </Typography>
              </View>
            </View>
          </View>

          {/* Schedule & Terms Details */}
          <View style={styles.sectionContainer}>
            <Typography style={styles.sectionHeading}>
              Terms & Schedule
            </Typography>

            <View style={styles.infoTable}>
              <View style={styles.tableRow}>
                <Typography style={styles.rowLabel}>Start Date</Typography>
                <Typography style={styles.rowValue}>
                  {obligation.start_date}
                </Typography>
              </View>

              <View style={styles.tableRow}>
                <Typography style={styles.rowLabel}>Term Duration</Typography>
                <Typography style={styles.rowValue}>
                  {obligation.term_months} Months
                </Typography>
              </View>

              <View style={styles.tableRow}>
                <Typography style={styles.rowLabel}>Payment Due Day</Typography>
                <Typography style={styles.rowValue}>
                  {obligation.due_day_of_month}th of every month
                </Typography>
              </View>

              <View style={styles.tableRow}>
                <Typography style={styles.rowLabel}>Source</Typography>
                <Typography style={[styles.rowValue, styles.capitalizeText]}>
                  {obligation.source.replace('_', ' ')}
                </Typography>
              </View>

              <View style={[styles.tableRow, styles.noBorderRow]}>
                <Typography style={styles.rowLabel}>Created</Typography>
                <Typography style={styles.rowValueMuted}>
                  {formatDate(obligation.created_at)}
                </Typography>
              </View>
            </View>
          </View>

          {/* Actions */}
          <View style={styles.actions}>
            <Button
              title="Edit Obligation"
              variant="outline"
              onPress={() => {
                onClose();
                onEdit(obligation);
              }}
              style={styles.actionButton}
            />

            <Button
              title="Delete Obligation"
              variant="danger"
              isLoading={isDeleting}
              onPress={() => onDelete(obligation)}
              style={styles.actionButton}
            />
          </View>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  closeButton: {
    padding: spacing.xs,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: spacing.lg,
  },
  heroBox: {
    backgroundColor: '#02262D',
    borderRadius: 20,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  heroTop: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  heroIconBadge: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  heroTitleCol: {
    flex: 1,
    marginRight: spacing.sm,
  },
  heroItemName: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 2,
  },
  heroProviderText: {
    fontSize: 12,
    color: '#94A3B8',
  },
  heroDivider: {
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    marginVertical: spacing.md,
  },
  heroAmountsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  amountCol: {
    flex: 1,
  },
  amountColRight: {
    alignItems: 'flex-end',
  },
  heroAmountLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
    color: '#94A3B8',
    marginBottom: 4,
  },
  heroInstallmentAmount: {
    fontSize: 22,
    fontWeight: '700',
    color: '#2DD4BF',
    fontVariant: ['tabular-nums'],
  },
  heroTotalAmount: {
    fontSize: 16,
    fontWeight: '600',
    color: '#F1F5F9',
    fontVariant: ['tabular-nums'],
  },
  sectionContainer: {
    marginBottom: spacing.xl,
  },
  sectionHeading: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
    letterSpacing: -0.1,
    marginBottom: spacing.sm,
  },
  infoTable: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.md - 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  noBorderRow: {
    borderBottomWidth: 0,
  },
  rowLabel: {
    fontSize: 13,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  rowValue: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  rowValueMuted: {
    fontSize: 12,
    color: colors.textMuted,
  },
  capitalizeText: {
    textTransform: 'capitalize',
  },
  actions: {
    gap: spacing.md,
    marginBottom: spacing.xl,
  },
  actionButton: {
    width: '100%',
  },
});
