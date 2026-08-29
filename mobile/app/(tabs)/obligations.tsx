import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  RefreshControl,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { obligationsApi } from '@/api/obligations';
import { ObligationResponse } from '@/types/obligation';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { ObligationCard } from '@/components/obligations/ObligationCard';
import { ObligationFormModal } from '@/components/obligations/ObligationFormModal';
import { ObligationDetailModal } from '@/components/obligations/ObligationDetailModal';
import { colors, spacing } from '@/constants/theme';

export default function ObligationsScreen() {
  const queryClient = useQueryClient();

  const [selectedObligation, setSelectedObligation] =
    useState<ObligationResponse | null>(null);
  const [formModalVisible, setFormModalVisible] = useState(false);
  const [editingObligation, setEditingObligation] =
    useState<ObligationResponse | null>(null);

  const {
    data: obligations,
    isLoading,
    isError,
    error,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ['obligations'],
    queryFn: obligationsApi.getObligations,
  });

  const deleteMutation = useMutation({
    mutationFn: obligationsApi.deleteObligation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['obligations'] });
      setSelectedObligation(null);
    },
    onError: (err: any) => {
      Alert.alert(
        'Deletion Failed',
        err?.message || 'Unable to delete obligation. Please try again.'
      );
    },
  });

  const handleOpenAdd = () => {
    setEditingObligation(null);
    setFormModalVisible(true);
  };

  const handleOpenEdit = (obligation: ObligationResponse) => {
    setEditingObligation(obligation);
    setFormModalVisible(true);
  };

  const handleDeleteConfirm = (obligation: ObligationResponse) => {
    Alert.alert(
      'Delete Obligation',
      `Are you sure you want to delete "${obligation.item_name}"? This action cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => deleteMutation.mutate(obligation.id),
        },
      ]
    );
  };

  const renderHeader = () => (
    <View style={styles.header}>
      <View style={styles.headerTitleCol}>
        <Typography variant="h1">Obligations</Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
          Track installments & commitments
        </Typography>
      </View>
      <TouchableOpacity
        onPress={handleOpenAdd}
        style={styles.addButton}
        activeOpacity={0.8}
      >
        <Typography variant="bodyBold" color={colors.textInverse}>
          + Add
        </Typography>
      </TouchableOpacity>
    </View>
  );

  if (isLoading && !isRefetching) {
    return (
      <ScreenWrapper>
        {renderHeader()}
        <LoadingIndicator message="Loading obligations..." />
      </ScreenWrapper>
    );
  }

  if (isError) {
    return (
      <ScreenWrapper scrollable>
        {renderHeader()}
        <ErrorBanner
          message={
            (error as any)?.message ||
            'Failed to load obligations. Please check your connection.'
          }
        />
        <Button title="Try Again" onPress={() => refetch()} style={styles.retryButton} />
      </ScreenWrapper>
    );
  }

  const items = obligations || [];

  return (
    <ScreenWrapper>
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        ListHeaderComponent={renderHeader}
        renderItem={({ item }) => (
          <ObligationCard
            obligation={item}
            onPress={(ob) => setSelectedObligation(ob)}
          />
        )}
        ListEmptyComponent={
          <Card style={styles.emptyCard}>
            <Typography variant="hero" align="center" style={styles.emptyIcon}>
              📋
            </Typography>
            <Typography variant="h2" align="center" style={styles.emptyTitle}>
              No Obligations Yet
            </Typography>
            <Typography
              variant="body"
              color={colors.textSecondary}
              align="center"
              style={styles.emptyText}
            >
              Add your loans, installments, and regular financial commitments to start tracking your payments.
            </Typography>
            <Button
              title="Add Your First Obligation"
              onPress={handleOpenAdd}
              style={styles.emptyButton}
            />
          </Card>
        }
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      />

      <ObligationFormModal
        visible={formModalVisible}
        onClose={() => setFormModalVisible(false)}
        initialData={editingObligation}
        onSuccess={() => {
          if (selectedObligation && editingObligation) {
            setSelectedObligation(null);
          }
        }}
      />

      <ObligationDetailModal
        visible={!!selectedObligation}
        obligation={selectedObligation}
        onClose={() => setSelectedObligation(null)}
        onEdit={handleOpenEdit}
        onDelete={handleDeleteConfirm}
        isDeleting={deleteMutation.isPending}
      />
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  listContent: {
    padding: spacing.md,
    flexGrow: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
    paddingTop: spacing.xs,
  },
  headerTitleCol: {
    flex: 1,
    marginRight: spacing.sm,
  },
  subtitle: {
    marginTop: spacing.xs / 2,
  },
  addButton: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md + 2,
    borderRadius: 8,
  },
  retryButton: {
    marginTop: spacing.md,
  },
  emptyCard: {
    padding: spacing.xl,
    alignItems: 'center',
    marginTop: spacing.lg,
  },
  emptyIcon: {
    fontSize: 40,
    marginBottom: spacing.sm,
  },
  emptyTitle: {
    marginBottom: spacing.xs,
  },
  emptyText: {
    marginBottom: spacing.lg,
    lineHeight: 22,
  },
  emptyButton: {
    width: '100%',
  },
});
