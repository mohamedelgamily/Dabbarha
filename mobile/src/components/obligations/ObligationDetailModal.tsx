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
import { Card } from '@/components/common/Card';
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
          <Typography variant="h2">Obligation Details</Typography>
          <TouchableOpacity
            onPress={onClose}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            style={styles.closeButton}
            accessibilityRole="button"
            accessibilityLabel="Close"
          >
            <Icon name="x" size={20} tone="secondary" />
          </TouchableOpacity>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <Card style={styles.summaryCard}>
            <View style={styles.summaryTop}>
              <View style={styles.summaryIconWrap}>
                <Icon name={pickCategoryIcon(obligation.category)} size={22} tone="primary" />
              </View>
              <View style={styles.summaryTitleCol}>
                <Typography variant="h1" style={styles.itemName}>
                  {obligation.item_name}
                </Typography>
                <Typography variant="body" color={colors.textSecondary}>
                  {obligation.provider} · {obligation.category}
                </Typography>
              </View>
              <Badge label={obligation.status} variant={badgeVariant} />
            </View>

            <View style={styles.divider} />

            <View style={styles.amountGrid}>
              <View style={styles.amountBox}>
                <Typography variant="caption" color={colors.textMuted}>
                  Monthly Installment
                </Typography>
                <Typography variant="h2" color={colors.primary} style={styles.amountText}>
                  {formatCurrency(obligation.monthly_installment_amount, currency)}
                </Typography>
              </View>

              <View style={styles.amountBox}>
                <Typography variant="caption" color={colors.textMuted}>
                  Total Amount
                </Typography>
                <Typography variant="h2" style={styles.amountText}>
                  {formatCurrency(obligation.total_amount, currency)}
                </Typography>
              </View>
            </View>
          </Card>

          <Card style={styles.infoCard}>
            <Typography variant="h3" style={styles.sectionTitle}>
              Schedule & Terms
            </Typography>

            <View style={styles.infoRow}>
              <Typography variant="body" color={colors.textSecondary}>
                Start Date
              </Typography>
              <Typography variant="bodyBold">
                {obligation.start_date}
              </Typography>
            </View>

            <View style={styles.infoRow}>
              <Typography variant="body" color={colors.textSecondary}>
                Term Duration
              </Typography>
              <Typography variant="bodyBold">
                {obligation.term_months} Months
              </Typography>
            </View>

            <View style={styles.infoRow}>
              <Typography variant="body" color={colors.textSecondary}>
                Payment Due Day
              </Typography>
              <Typography variant="bodyBold">
                {obligation.due_day_of_month} of every month
              </Typography>
            </View>

            <View style={styles.infoRow}>
              <Typography variant="body" color={colors.textSecondary}>
                Entry Source
              </Typography>
              <Typography variant="bodyBold" style={styles.sourceText}>
                {obligation.source.replace('_', ' ')}
              </Typography>
            </View>

            <View style={styles.divider} />

            <View style={styles.metaRow}>
              <View style={styles.metaItem}>
                <Icon name="clock" size={14} tone="muted" />
                <Typography variant="caption" color={colors.textMuted} style={styles.metaText}>
                  Created {formatDate(obligation.created_at)}
                </Typography>
              </View>
              <View style={styles.metaItem}>
                <Icon name="refresh" size={14} tone="muted" />
                <Typography variant="caption" color={colors.textMuted} style={styles.metaText}>
                  Updated {formatDate(obligation.updated_at)}
                </Typography>
              </View>
            </View>
          </Card>

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
  closeButton: {
    padding: spacing.xs,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: spacing.lg,
  },
  summaryCard: {
    marginBottom: spacing.md,
    borderRadius: borderRadius.xl,
  },
  summaryTop: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  summaryIconWrap: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  summaryTitleCol: {
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
  amountGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  amountBox: {
    flex: 1,
  },
  amountText: {
    marginTop: 2,
  },
  infoCard: {
    marginBottom: spacing.lg,
    borderRadius: borderRadius.xl,
  },
  sectionTitle: {
    marginBottom: spacing.md,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs + 2,
  },
  sourceText: {
    textTransform: 'capitalize',
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metaText: {
    marginLeft: spacing.xs,
  },
  actions: {
    gap: spacing.md,
    marginBottom: spacing.xl,
  },
  actionButton: {
    width: '100%',
  },
});
