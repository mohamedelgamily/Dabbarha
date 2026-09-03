import React, { useEffect, useState } from 'react';
import {
  Modal,
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { obligationSchema, ObligationFormData } from '@/schemas/obligation';
import { obligationsApi } from '@/api/obligations';
import {
  ObligationResponse,
  ObligationStatus,
  ObligationCreate,
  ObligationUpdate,
} from '@/types/obligation';
import { Typography } from '@/components/common/Typography';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Icon } from '@/components/common/Icon';
import { Segmented, type SegmentedOption } from '@/components/common/Segmented';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { getTodayDateString } from '@/utils/format';

interface ObligationFormModalProps {
  visible: boolean;
  onClose: () => void;
  initialData?: ObligationResponse | null;
  onSuccess?: () => void;
}

const statusOptions: SegmentedOption<ObligationStatus>[] = [
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'late', label: 'Late' },
  { value: 'defaulted', label: 'Defaulted' },
];

const defaultValues: ObligationFormData = {
  provider: '',
  item_name: '',
  category: '',
  total_amount: '',
  monthly_installment_amount: '',
  start_date: getTodayDateString(),
  term_months: '12',
  due_day_of_month: '1',
  status: 'active',
};

export function ObligationFormModal({
  visible,
  onClose,
  initialData,
  onSuccess,
}: ObligationFormModalProps) {
  const queryClient = useQueryClient();
  const [apiError, setApiError] = useState<string | null>(null);

  const isEditing = !!initialData;

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ObligationFormData>({
    resolver: zodResolver(obligationSchema),
    defaultValues,
  });

  useEffect(() => {
    if (visible) {
      setApiError(null);
      if (initialData) {
        reset({
          provider: initialData.provider,
          item_name: initialData.item_name,
          category: initialData.category,
          total_amount: String(initialData.total_amount),
          monthly_installment_amount: String(initialData.monthly_installment_amount),
          start_date: initialData.start_date,
          term_months: String(initialData.term_months),
          due_day_of_month: String(initialData.due_day_of_month),
          status: initialData.status as ObligationStatus,
        });
      } else {
        reset({ ...defaultValues, start_date: getTodayDateString() });
      }
    }
  }, [visible, initialData, reset]);

  const mutation = useMutation({
    mutationFn: async (data: ObligationFormData) => {
      if (isEditing && initialData) {
        const updatePayload: ObligationUpdate = {
          provider: data.provider.trim(),
          item_name: data.item_name.trim(),
          category: data.category.trim(),
          total_amount: Number(data.total_amount),
          monthly_installment_amount: Number(data.monthly_installment_amount),
          start_date: data.start_date.trim(),
          term_months: Number(data.term_months),
          due_day_of_month: Number(data.due_day_of_month),
          status: data.status,
        };
        return await obligationsApi.updateObligation(initialData.id, updatePayload);
      } else {
        const createPayload: ObligationCreate = {
          provider: data.provider.trim(),
          item_name: data.item_name.trim(),
          category: data.category.trim(),
          total_amount: Number(data.total_amount),
          monthly_installment_amount: Number(data.monthly_installment_amount),
          start_date: data.start_date.trim(),
          term_months: Number(data.term_months),
          due_day_of_month: Number(data.due_day_of_month),
          status: data.status,
          source: 'manual_entry',
        };
        return await obligationsApi.createObligation(createPayload);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['obligations'] });
      if (initialData) {
        queryClient.invalidateQueries({
          queryKey: ['obligation', initialData.id],
        });
      }
      onSuccess?.();
      onClose();
    },
    onError: (err: any) => {
      setApiError(err?.message || 'Failed to save obligation. Please check inputs.');
    },
  });

  const onSubmit = (data: ObligationFormData) => {
    setApiError(null);
    mutation.mutate(data);
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.modalContainer}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.container}
        >
          <View style={styles.header}>
            <Typography variant="h2">
              {isEditing ? 'Edit Obligation' : 'Add Obligation'}
            </Typography>
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
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <ErrorBanner
              message={apiError}
              onDismiss={() => setApiError(null)}
            />

            <Controller
              control={control}
              name="item_name"
              render={({ field: { onChange, onBlur, value } }) => (
                <Input
                  label="Item / Purpose *"
                  placeholder="e.g. iPhone 15, Car Installment"
                  value={value}
                  onChangeText={(text) => {
                    if (apiError) setApiError(null);
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.item_name?.message}
                />
              )}
            />

            <Controller
              control={control}
              name="provider"
              render={({ field: { onChange, onBlur, value } }) => (
                <Input
                  label="Provider / Bank / Vendor *"
                  placeholder="e.g. ValU, Aman, NBE"
                  value={value}
                  onChangeText={(text) => {
                    if (apiError) setApiError(null);
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.provider?.message}
                />
              )}
            />

            <Controller
              control={control}
              name="category"
              render={({ field: { onChange, onBlur, value } }) => (
                <Input
                  label="Category *"
                  placeholder="e.g. Electronics, Vehicle, Housing"
                  value={value}
                  onChangeText={(text) => {
                    if (apiError) setApiError(null);
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.category?.message}
                />
              )}
            />

            <View style={styles.row}>
              <View style={styles.halfCol}>
                <Controller
                  control={control}
                  name="total_amount"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <Input
                      label="Total Amount *"
                      placeholder="0.00"
                      keyboardType="decimal-pad"
                      value={value}
                      onChangeText={(text) => {
                        if (apiError) setApiError(null);
                        onChange(text);
                      }}
                      onBlur={onBlur}
                      error={errors.total_amount?.message}
                    />
                  )}
                />
              </View>
              <View style={styles.halfCol}>
                <Controller
                  control={control}
                  name="monthly_installment_amount"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <Input
                      label="Monthly Amount *"
                      placeholder="0.00"
                      keyboardType="decimal-pad"
                      value={value}
                      onChangeText={(text) => {
                        if (apiError) setApiError(null);
                        onChange(text);
                      }}
                      onBlur={onBlur}
                      error={errors.monthly_installment_amount?.message}
                    />
                  )}
                />
              </View>
            </View>

            <View style={styles.row}>
              <View style={styles.halfCol}>
                <Controller
                  control={control}
                  name="term_months"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <Input
                      label="Term (Months) *"
                      placeholder="12"
                      keyboardType="number-pad"
                      value={value}
                      onChangeText={(text) => {
                        if (apiError) setApiError(null);
                        onChange(text);
                      }}
                      onBlur={onBlur}
                      error={errors.term_months?.message}
                    />
                  )}
                />
              </View>
              <View style={styles.halfCol}>
                <Controller
                  control={control}
                  name="due_day_of_month"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <Input
                      label="Due Day (1-31) *"
                      placeholder="1"
                      keyboardType="number-pad"
                      value={value}
                      onChangeText={(text) => {
                        if (apiError) setApiError(null);
                        onChange(text);
                      }}
                      onBlur={onBlur}
                      error={errors.due_day_of_month?.message}
                    />
                  )}
                />
              </View>
            </View>

            <Controller
              control={control}
              name="start_date"
              render={({ field: { onChange, onBlur, value } }) => (
                <Input
                  label="Start Date (YYYY-MM-DD) *"
                  placeholder="2026-08-29"
                  value={value}
                  onChangeText={(text) => {
                    if (apiError) setApiError(null);
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.start_date?.message}
                  helperText="Format: YYYY-MM-DD"
                />
              )}
            />

            <View style={styles.statusSection}>
              <Typography variant="label" style={styles.statusLabel}>
                Status
              </Typography>
              <Controller
                control={control}
                name="status"
                render={({ field: { onChange, value } }) => (
                  <Segmented
                    value={value}
                    options={statusOptions}
                    onChange={onChange}
                  />
                )}
              />
            </View>

            <Button
              title={isEditing ? 'Save Changes' : 'Create Obligation'}
              onPress={handleSubmit(onSubmit)}
              isLoading={mutation.isPending}
              style={styles.submitButton}
            />
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
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
  row: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  halfCol: {
    flex: 1,
  },
  statusSection: {
    marginBottom: spacing.lg,
  },
  statusLabel: {
    marginBottom: spacing.xs,
  },
  submitButton: {
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
  },
});
