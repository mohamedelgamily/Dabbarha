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
import { colors, spacing } from '@/constants/theme';

interface ObligationDetailModalProps {
  visible: boolean;
  onClose: () => void;
  obligation: ObligationResponse | null;
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

export function ObligationDetailModal({
  visible,
  onClose,
  obligation,
  onEdit,
  onDelete,
  isDeleting = false,
}: ObligationDetailModalProps) {
  if (!obligation) return null;

  const badgeVariant =
    statusBadgeVariant[obligation.status as ObligationStatus] || 'neutral';

  const formatCurrency = (amount: string | number) => {
    const num = Number(amount);
    if (isNaN(num)) return `${amount} EGP`;
    return `${num.toLocaleString()} EGP`;
  };

  const formatDate = (isoString?: string) => {
    if (!isoString) return 'N/A';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

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
          >
            <Typography variant="bodyBold" color={colors.textSecondary}>
              ✕
            </Typography>
          </TouchableOpacity>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <Card style={styles.summaryCard}>
            <View style={styles.summaryTop}>
              <View style={styles.summaryTitleCol}>
                <Typography variant="h1" style={styles.itemName}>
                  {obligation.item_name}
                </Typography>
                <Typography variant="body" color={colors.textSecondary}>
                  {obligation.provider} • {obligation.category}
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
                  {formatCurrency(obligation.monthly_installment_amount)}
                </Typography>
              </View>

              <View style={styles.amountBox}>
                <Typography variant="caption" color={colors.textMuted}>
                  Total Amount
                </Typography>
                <Typography variant="h2" style={styles.amountText}>
                  {formatCurrency(obligation.total_amount)}
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
                {obligation.due_day_of_month}th of every month
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

            <View style={styles.infoRow}>
              <Typography variant="caption" color={colors.textMuted}>
                Created: {formatDate(obligation.created_at)}
              </Typography>
              <Typography variant="caption" color={colors.textMuted}>
                Updated: {formatDate(obligation.updated_at)}
              </Typography>
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
  },
  summaryTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  summaryTitleCol: {
    flex: 1,
    marginRight: spacing.sm,
  },
  itemName: {
    marginBottom: spacing.xs / 2,
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
    marginTop: spacing.xs / 2,
  },
  infoCard: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    marginBottom: spacing.md,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs + 2,
  },
  sourceText: {
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
