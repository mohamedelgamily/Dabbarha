import { t, categoryLabel, monthCount, formatCount, normalizeNumericInput, translateMessage, isArabic } from '@/i18n';
import React, { useEffect, useRef, useState } from 'react';
import {
  Modal,
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  TextInput,
  Keyboard,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useForm, Controller, type UseFormReturn } from 'react-hook-form';
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
import { colors, spacing, borderRadius, typography } from '@/constants/theme';
import { getTodayDateString, formatCurrency, formatDate } from '@/utils/format';
import { useAuthStore } from '@/store/authStore';
import { Building2, Laptop, Tag, Car, House, GraduationCap, ChevronDown, CalendarDays, ArrowRight, Check } from 'lucide-react-native';

interface ObligationFormModalProps {
  visible: boolean;
  onClose: () => void;
  initialData?: ObligationResponse | null;
  onSuccess?: () => void;
}

const getStatusOptions = (): SegmentedOption<ObligationStatus>[] => [
  { value: 'active', label: t("Active") },
  { value: 'completed', label: t("Completed") },
  { value: 'late', label: t("Late") },
  { value: 'defaulted', label: t("Defaulted") },
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

  const form = useForm<ObligationFormData>({ resolver: zodResolver(obligationSchema), defaultValues, mode: isEditing ? 'onSubmit' : 'onChange' });
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = form;

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
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      queryClient.invalidateQueries({ queryKey: ['forecast'] });
      if (initialData) {
        queryClient.invalidateQueries({
          queryKey: ['obligation', initialData.id],
        });
      }
      onSuccess?.();
      onClose();
    },
    onError: (err: any) => {
      if (!isEditing && Array.isArray(err?.detail)) {
        for (const issue of err.detail) {
          const fieldName = issue.loc?.[issue.loc.length - 1];
          if (typeof fieldName === 'string' && fieldName in defaultValues) {
            form.setError(fieldName as keyof ObligationFormData, { type: 'server', message: translateMessage(issue.msg) });
          }
        }
      }
      setApiError(err?.message || t("Failed to save obligation. Please check inputs."));
    },
  });

  const onSubmit = (data: ObligationFormData) => {
    setApiError(null);
    mutation.mutate(data);
  };

  if (!isEditing) {
    return <CreationFlow visible={visible} onClose={onClose} form={form} onSubmit={onSubmit}
      isPending={mutation.isPending} apiError={apiError} clearError={() => setApiError(null)} />;
  }
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
            <Typography style={styles.headerTitle}>
              {isEditing ? t("Edit Commitment") : t("New Commitment")}
            </Typography>
            <TouchableOpacity
              onPress={onClose}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              style={styles.closeButton}
              accessibilityRole="button"
              accessibilityLabel={t("Close")}
            >
              <Icon name="x" size={20} color={colors.textSecondary} />
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
                  label={t("Item / Purpose *")}
                  placeholder={t("e.g. MacBook Pro, Car Installment")}
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
                  label={t("Provider / Bank / Vendor *")}
                  placeholder={t("e.g. ValU, Aman, NBE, Commercial Bank")}
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
                  label={t("Category *")}
                  placeholder={t("e.g. Electronics, Vehicle, Housing, Education")}
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
                      label={t("Total Amount *")}
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
                      label={t("Monthly Amount *")}
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
                      label={t("Term (Months) *")}
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
                      label={t("Due Day (1-31) *")}
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
                  dateInput label={t("Start Date (YYYY-MM-DD) *")}
                  placeholder="2026-09-01"
                  value={value}
                  onChangeText={(text) => {
                    if (apiError) setApiError(null);
                    onChange(text);
                  }}
                  onBlur={onBlur}
                  error={errors.start_date?.message}
                  helperText={t("Format: YYYY-MM-DD")}
                />
              )}
            />

            <View style={styles.statusSection}>
              <Typography variant="label" style={styles.statusLabel}>
                {t("Status")}</Typography>
              <Controller
                control={control}
                name="status"
                render={({ field: { onChange, value } }) => (
                  <Segmented
                    value={value}
                    options={getStatusOptions()}
                    onChange={onChange}
                  />
                )}
              />
            </View>

            <Button
              title={isEditing ? t("Save Changes") : t("Create Commitment")}
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

const detailFields = ['item_name', 'provider', 'category'] as const;
const paymentFields = ['total_amount', 'monthly_installment_amount', 'term_months', 'due_day_of_month', 'start_date', 'status'] as const;
const categoryChoices = [
  { label: 'Electronics', icon: Laptop },
  { label: 'Vehicle', icon: Car },
  { label: 'Housing', icon: House },
  { label: 'Education', icon: GraduationCap },
];

function readableDate(value: string) { return formatDate(value); }

function CreationFlow({ visible, onClose, form, onSubmit, isPending, apiError, clearError }: {
  visible: boolean;
  onClose: () => void;
  form: UseFormReturn<ObligationFormData>;
  onSubmit: (data: ObligationFormData) => void;
  isPending: boolean;
  apiError: string | null;
  clearError: () => void;
}) {
  const [step, setStep] = useState(0);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [customCategory, setCustomCategory] = useState(false);
  const [dateEditing, setDateEditing] = useState(false);
  const [focused, setFocused] = useState<string | null>(null);
  const scroll = useRef<ScrollView>(null);
  const submitting = useRef(false);
  const { width, fontScale } = useWindowDimensions();
  const currency = useAuthStore((state) => state.user?.currency || 'EGP');
  const values = form.watch();
  const errors = form.formState.errors;
  const stacked = width < 360 || fontScale > 1.15;
  const fields = step === 0 ? detailFields : paymentFields;
  // Use the existing schema verbatim; never round or adjust entered amounts.
  const parsed = obligationSchema.safeParse(values);
  const stepValid = (parsed.success || !parsed.error.issues.some((issue) =>
    step === 2 || (fields as readonly string[]).includes(String(issue.path[0])))) &&
    !Object.entries(errors).some(([name, error]) => error?.type === 'server' && (step === 2 || (fields as readonly string[]).includes(name)));
  useEffect(() => {
    if (visible) {
      setStep(0);
      setCategoryOpen(false);
      setCustomCategory(false);
      setDateEditing(false);
      submitting.current = false;
    }
  }, [visible]);
  useEffect(() => { if (!isPending) submitting.current = false; }, [isPending, apiError]);
  const moveTo = (next: number) => {
    Keyboard.dismiss();
    setFocused(null);
    setStep(next);
    scroll.current?.scrollTo({ y: 0, animated: false });
  };
  const advance = async () => {
    if (isPending || submitting.current) return;
    if (step < 2) {
      if (await form.trigger([...fields])) moveTo(step + 1);
      return;
    }
    submitting.current = true;
    await form.handleSubmit(onSubmit, (fieldErrors) => {
      submitting.current = false;
      moveTo(detailFields.some((name) => fieldErrors[name]) ? 0 : 1);
    })();
  };
  useEffect(() => {
    if (!apiError) return;
    const currentErrors = form.formState.errors;
    if (detailFields.some((name) => currentErrors[name]?.type === 'server')) {
      setStep(0);
    } else if (paymentFields.some((name) => currentErrors[name]?.type === 'server')) {
      setStep(1);
    }
    scroll.current?.scrollTo({ y: 0, animated: true });
  }, [apiError, form]);
  const update = (name: keyof ObligationFormData, value: string) => {
    clearError();
    form.setValue(name, value as ObligationFormData[typeof name], { shouldValidate: true, shouldDirty: true, shouldTouch: true });
  };
  const field = (name: Exclude<keyof ObligationFormData, 'status'>, label: string, placeholder: string,
    options: { money?: boolean; numeric?: boolean; icon?: React.ReactNode; hint?: string } = {}) => (
    <Controller key={name} control={form.control} name={name} render={({ field: input }) => (
      <View style={flow.field}>
        <Typography style={flow.label}>{label} <Typography style={flow.required}>*</Typography></Typography>
        <View style={[flow.inputShell, focused === name && flow.focused, !!errors[name] && flow.invalid]}>
          {options.icon}
          <TextInput
            ref={input.ref}
            value={input.value}
            onChangeText={(value) => { clearError(); input.onChange(options.money || options.numeric || name === 'start_date' ? normalizeNumericInput(value) : value); }}
            onFocus={() => setFocused(name)}
            onBlur={() => { setFocused(null); input.onBlur(); }}
            accessibilityLabel={label}
            accessibilityHint={translateMessage(errors[name]?.message) || options.hint}
            placeholder={placeholder}
            placeholderTextColor="#8B9B9E"
            keyboardType={options.money ? 'decimal-pad' : options.numeric ? 'number-pad' : 'default'}
            autoCapitalize={name === 'start_date' ? 'none' : 'sentences'}
            autoCorrect={!options.money && !options.numeric && name !== 'start_date'}
            style={[flow.input, (options.money || options.numeric) && flow.numeric, { textAlign: 'left', direction: options.money || options.numeric || name === 'start_date' ? 'ltr' : isArabic() ? 'rtl' : 'ltr', writingDirection: options.money || options.numeric || name === 'start_date' ? 'ltr' : 'auto' }, isArabic() && !options.money && !options.numeric && name !== 'start_date' && { fontFamily: 'NotoNaskhArabic', lineHeight: 27 }]}
          />
          {options.money && <View style={flow.currencyPill}><Typography style={flow.currency}>{currency}</Typography></View>}
        </View>
        {errors[name]?.message && <Typography accessibilityLiveRegion="polite" style={flow.error}>{translateMessage(errors[name]?.message)}</Typography>}
        {options.hint && !errors[name] && <Typography style={flow.hint}>{options.hint}</Typography>}
      </View>
    )} />
  );
  const selectedCategory = categoryChoices.find((choice) => choice.label === values.category);
  const CategoryIcon = selectedCategory?.icon || Tag;
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <SafeAreaView style={flow.safe}>
        <KeyboardAvoidingView style={flow.sheet} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
          <View style={flow.handle} />
          <View style={flow.header}>
            <TouchableOpacity onPress={onClose} accessibilityRole="button" accessibilityLabel={t("Close New Commitment")} style={flow.close}>
              <Icon name="x" size={20} color="#294344" />
            </TouchableOpacity>
            <View style={flow.heading}>
              <Typography style={flow.title}>{t("New Commitment")}</Typography>
              <Typography style={flow.subtitle}>{t("Add a new financial commitment")}</Typography>
            </View>
            <View style={flow.headerBalance} />
          </View>
          <View style={flow.stepper} accessibilityLabel={t('Step {step} of 3: {label}', { step: formatCount(step + 1), label: [t('Details'), t('Payment'), t('Review')][step] })}>
            {[t("Details"), t("Payment"), t("Review")].map((label, index) => (
              <View key={label} style={flow.stepItem}>
                {index > 0 && <View style={[flow.connector, index <= step && flow.connectorDone]} />}
                <View style={[flow.stepCircle, index <= step && flow.stepActive]}>
                  {index < step ? <Check size={12} color="#F7F6EF" /> : <Typography style={[flow.stepNumber, index === step && flow.stepNumberActive]}>{formatCount(index + 1)}</Typography>}
                </View>
                <Typography style={[flow.stepLabel, index === step && flow.stepLabelActive]}>{label}</Typography>
              </View>
            ))}
          </View>
          <ScrollView ref={scroll} style={flow.scroll} contentContainerStyle={flow.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag" showsVerticalScrollIndicator={false}>
            <ErrorBanner message={apiError} onDismiss={clearError} />
            {step === 0 && <>
              {field('item_name', t("Item / Purpose"), t("e.g. MacBook Pro, Car installment"), { icon: <Laptop size={19} color="#718B8D" /> })}
              {field('provider', t("Provider / Bank / Vendor"), t("e.g. ValU, Aman, NBE"), { icon: <Building2 size={19} color="#718B8D" /> })}
              <View style={flow.field}>
                <Typography style={flow.label}>{t("Category")} <Typography style={flow.required}>*</Typography></Typography>
                <TouchableOpacity style={[flow.inputShell, categoryOpen && flow.focused, !!errors.category && flow.invalid]} onPress={() => { Keyboard.dismiss(); setCategoryOpen(!categoryOpen); }} accessibilityRole="button" accessibilityLabel={t("Category: ") + (categoryLabel(values.category) || t("Select category"))} accessibilityState={{ expanded: categoryOpen }}>
                  <CategoryIcon size={19} color="#718B8D" />
                  <Typography style={[flow.selectText, !values.category && flow.placeholder]}>{categoryLabel(values.category) || t("Select category")}</Typography>
                  <ChevronDown size={17} color="#718B8D" />
                </TouchableOpacity>
                {categoryOpen && <View style={flow.options}>
                  {categoryChoices.map(({ label, icon: ChoiceIcon }) => (
                    <TouchableOpacity key={label} style={flow.option} accessibilityRole="button" accessibilityState={{ selected: values.category === label }} onPress={() => { update('category', label); setCustomCategory(false); setCategoryOpen(false); }}>
                      <ChoiceIcon size={18} color="#52756D" /><Typography style={flow.optionText}>{categoryLabel(label)}</Typography>
                      {values.category === label && <Check size={17} color="#285F53" />}
                    </TouchableOpacity>
                  ))}
                  <TouchableOpacity style={flow.option} accessibilityRole="button" onPress={() => { setCustomCategory(true); setCategoryOpen(false); }}>
                    <Tag size={18} color="#52756D" /><Typography style={flow.optionText}>{t("Custom category")}</Typography>
                  </TouchableOpacity>
                </View>}
                {!customCategory && errors.category && <Typography style={flow.error}>{translateMessage(errors.category.message)}</Typography>}
              </View>
              {customCategory && field('category', t("Custom category"), t("Enter a category"), { icon: <Tag size={19} color="#718B8D" /> })}
            </>}
            {step === 1 && <>
              <View style={[flow.row, stacked && flow.stacked]}>
                <View style={flow.column}>{field('total_amount', t("Total Amount"), '0.00', { money: true })}</View>
                <View style={flow.column}>{field('monthly_installment_amount', t("Monthly Amount"), '0.00', { money: true })}</View>
              </View>
              <View style={[flow.row, stacked && flow.stacked]}>
                <View style={flow.column}>{field('term_months', t("Term (Months)"), '12', { numeric: true, icon: <CalendarDays size={18} color="#718B8D" /> })}</View>
                <View style={flow.column}>{field('due_day_of_month', t("Due Day (1–31)"), '1', { numeric: true, icon: <CalendarDays size={18} color="#718B8D" /> })}</View>
              </View>
              <View style={flow.quickTerms}>
                <Typography style={flow.hint}>{t("Quick term")}</Typography>
                {[3, 6, 12, 24].map((term) => <TouchableOpacity key={term} style={[flow.term, values.term_months === String(term) && flow.chipSelected]} accessibilityRole="button" accessibilityLabel={monthCount(term)} accessibilityState={{ selected: values.term_months === String(term) }} onPress={() => update('term_months', String(term))}>
                  <Typography style={flow.chipText}>{formatCount(term)}</Typography>
                </TouchableOpacity>)}
              </View>
              {dateEditing ? <>
                {field('start_date', t("Start Date"), 'YYYY-MM-DD', { icon: <CalendarDays size={19} color="#718B8D" />, hint: t("Enter year-month-day, e.g. 2026-09-06") })}
                <TouchableOpacity style={flow.dateDone} accessibilityRole="button" onPress={async () => { if (await form.trigger('start_date')) { setDateEditing(false); Keyboard.dismiss(); } }}>
                  <Typography style={flow.link}>{t("Done editing date")}</Typography>
                </TouchableOpacity>
              </> : <View style={flow.field}>
                <Typography style={flow.label}>{t("Start Date")} <Typography style={flow.required}>*</Typography></Typography>
                <TouchableOpacity style={[flow.inputShell, !!errors.start_date && flow.invalid]} accessibilityRole="button" accessibilityLabel={t('Start date: {date}. Edit date', { date: readableDate(values.start_date) })} onPress={() => setDateEditing(true)}>
                  <CalendarDays size={19} color="#718B8D" />
                  <Typography style={flow.selectText}>{readableDate(values.start_date)}</Typography>
                  <Typography style={flow.link}>{t("Edit")}</Typography>
                </TouchableOpacity>
                {errors.start_date && <Typography style={flow.error}>{translateMessage(errors.start_date.message)}</Typography>}
              </View>}
              <Typography style={flow.label}>{t("Status")}</Typography>
              <View style={flow.statuses}>
                {getStatusOptions().map((option) => <TouchableOpacity key={option.value} style={[flow.statusChip, values.status === option.value && flow.chipSelected]} accessibilityRole="radio" accessibilityState={{ checked: values.status === option.value }} onPress={() => update('status', option.value)}>
                  <View style={[flow.statusDot, values.status === option.value && flow.statusDotSelected]} />
                  <Typography style={flow.chipText}>{option.label}</Typography>
                </TouchableOpacity>)}
              </View>
              {errors.status && <Typography style={flow.error}>{translateMessage(errors.status.message)}</Typography>}
            </>}
            {step === 2 && <>
              <View style={flow.reviewTop}>
                <View style={flow.reviewIcon}><CategoryIcon size={24} color="#376E5F" /></View>
                <Typography style={flow.reviewTitle}>{values.item_name}</Typography>
                <Typography style={flow.reviewCategory}>{categoryLabel(values.category)}</Typography>
              </View>
              <View style={flow.reviewAmounts}>
                <Typography style={flow.reviewKicker}>{t("Monthly commitment")}</Typography>
                <Typography style={flow.reviewAmount}>{formatCurrency(values.monthly_installment_amount, currency)}</Typography>
                <Typography style={flow.reviewTotal}>{t("Total ·")} {formatCurrency(values.total_amount, currency)}</Typography>
              </View>
              {[
                [t("Term"), monthCount(values.term_months)],
                [t("Due"), t('Day {day} of each month', { day: formatCount(values.due_day_of_month) })],
                [t("Start"), readableDate(values.start_date)],
                [t("Provider"), values.provider],
                [t("Status"), getStatusOptions().find((option) => option.value === values.status)?.label || values.status],
              ].map(([label, value]) => <View key={label} style={flow.reviewRow}>
                <Typography style={flow.reviewLabel}>{label}</Typography>
                <Typography style={flow.reviewValue}>{value}</Typography>
              </View>)}
              <Typography style={flow.reviewNote}>{t("Check your details before creating this commitment.")}</Typography>
            </>}
          </ScrollView>
          <View style={flow.footer}>
            {step > 0 && <TouchableOpacity disabled={isPending} onPress={() => moveTo(step - 1)} style={flow.back} accessibilityRole="button" accessibilityLabel={t("Back to previous step")}><Typography style={flow.link}>{t("Back")}</Typography></TouchableOpacity>}
            <View style={flow.ctaWrap}>
              <Button title={step === 0 ? t("Continue") : step === 1 ? t("Review") : t("Create Commitment")} onPress={advance}
                disabled={!stepValid || isPending} isLoading={isPending} style={flow.cta}
                textStyle={flow.ctaText} accessibilityRole="button" accessibilityState={{ disabled: !stepValid || isPending, busy: isPending }} />
              {step < 2 && <View pointerEvents="none" style={flow.ctaArrow}><ArrowRight style={isArabic() ? { transform: [{ scaleX: -1 }] } : undefined} size={18} color="#EEF4EE" /></View>}
            </View>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  );
}

const flow = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F8F6F2' },
  sheet: { flex: 1, backgroundColor: '#F8F6F2', borderTopLeftRadius: 30, borderTopRightRadius: 30, overflow: 'hidden' },
  handle: { width: 42, height: 4, borderRadius: 2, backgroundColor: '#D2D5CF', alignSelf: 'center', marginTop: 9, marginBottom: 10 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, gap: 8 },
  close: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#EEEDE8', alignItems: 'center', justifyContent: 'center' },
  headerBalance: { width: 28 },
  heading: { flex: 1 },
  title: { fontFamily: typography.fontFamily, ...typography.title, fontSize: 23, lineHeight: 30, color: '#02262D', letterSpacing: -0.6, textAlign: 'center' },
  subtitle: { fontSize: 12, lineHeight: 18, color: '#7A898B', textAlign: 'center', marginTop: 3 },
  stepper: { flexDirection: 'row', paddingHorizontal: 25, marginTop: 23, marginBottom: 20 },
  stepItem: { flex: 1, alignItems: 'center' },
  connector: { position: 'absolute', height: 1, backgroundColor: '#DFE1DA', width: '78%', end: '61%', top: 11 },
  connectorDone: { backgroundColor: '#719F8B' },
  stepCircle: { width: 23, height: 23, borderRadius: 12, backgroundColor: '#DDDED8', alignItems: 'center', justifyContent: 'center' },
  stepActive: { backgroundColor: '#073E3D' },
  stepNumber: { fontSize: 11, lineHeight: 16, color: '#6D7D79' },
  stepNumberActive: { color: '#FFFFFF' },
  stepLabel: { fontSize: 11, lineHeight: 16, color: '#7E8B8C', marginTop: 5 },
  stepLabelActive: { color: '#174A43', fontWeight: '600' },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 20, paddingBottom: 24 },
  field: { marginBottom: 17 },
  label: { fontSize: 12, lineHeight: 18, color: '#34474A', marginBottom: 6, fontWeight: '500' },
  required: { color: '#537F73', fontSize: 12 },
  inputShell: { minHeight: 51, flexDirection: 'row', alignItems: 'center', gap: 9, borderWidth: 1, borderColor: '#E0E5E2', backgroundColor: '#FDFDFC', borderRadius: 12, paddingHorizontal: 12 },
  focused: { borderColor: '#50897B', backgroundColor: '#F8FCF8' },
  invalid: { borderColor: '#BC6652' },
  input: { fontFamily: typography.fontFamily, flex: 1, minWidth: 0, paddingVertical: 13, fontSize: 14, color: '#183A3E' },
  numeric: { fontVariant: ['tabular-nums'], fontSize: 16 },
  currencyPill: { backgroundColor: '#EDF0EB', paddingHorizontal: 6, paddingVertical: 3, borderRadius: 5 },
  currency: { fontSize: 10, lineHeight: 15, color: '#617779' },
  error: { fontSize: 12, lineHeight: 17, color: '#AD493C', marginTop: 5 },
  hint: { fontSize: 11, lineHeight: 16, color: '#7A8987', marginTop: 4 },
  selectText: { flex: 1, fontSize: 14, lineHeight: 21, color: '#183A3E', paddingVertical: 12 },
  placeholder: { color: '#8B9B9E' },
  options: { borderWidth: 1, borderColor: '#E0E5E2', borderRadius: 12, backgroundColor: '#FDFDFC', padding: 5, marginTop: 7 },
  option: { flexDirection: 'row', gap: 12, alignItems: 'center', minHeight: 46, padding: 10 },
  optionText: { flex: 1, fontSize: 14, lineHeight: 20, color: '#304E4B' },
  row: { flexDirection: 'row', gap: 14 },
  stacked: { flexDirection: 'column', gap: 0 },
  column: { flex: 1, minWidth: 0 },
  quickTerms: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: -5, marginBottom: 19 },
  term: { minWidth: 44, minHeight: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#DFE5DC' },
  chipSelected: { backgroundColor: '#E1EEE4', borderColor: '#9CBEAE' },
  chipText: { fontSize: 12, lineHeight: 18, color: '#285148' },
  statuses: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  statusChip: { flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 44, paddingHorizontal: 13, paddingVertical: 8, borderRadius: 12, borderWidth: 1, borderColor: '#DFE5DC' },
  statusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#BAC7BF' },
  statusDotSelected: { backgroundColor: '#386D5D' },
  dateDone: { alignSelf: 'flex-start', paddingVertical: 10, marginTop: -12, marginBottom: 8 },
  link: { fontSize: 13, lineHeight: 20, color: '#285E51', fontWeight: '500' },
  footer: { paddingHorizontal: 20, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 14, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E2E5DC', backgroundColor: '#F8F6F2' },
  back: { minHeight: 48, justifyContent: 'center', paddingHorizontal: 8 },
  ctaWrap: { flex: 1 },
  cta: { minHeight: 52, borderRadius: 12, backgroundColor: '#02262D' },
  ctaText: { fontSize: 14, fontWeight: '500', paddingHorizontal: 12 },
  ctaArrow: { position: 'absolute', end: 18, top: 17 },
  reviewTop: { alignItems: 'center', paddingTop: 5, paddingBottom: 22 },
  reviewIcon: { width: 50, height: 50, borderRadius: 17, backgroundColor: '#E1EEE4', alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  reviewTitle: { fontFamily: typography.fontFamily, ...typography.title, fontSize: 27, lineHeight: 34, color: '#143E3B', textAlign: 'center' },
  reviewCategory: { fontSize: 13, lineHeight: 19, color: '#6E8580', marginTop: 4, textAlign: 'center' },
  reviewAmounts: { backgroundColor: '#073B3C', borderRadius: 19, padding: 20, marginBottom: 14 },
  reviewKicker: { fontSize: 12, lineHeight: 18, color: '#B9CFC3' },
  reviewAmount: { fontSize: 29, lineHeight: 38, fontVariant: ['tabular-nums'], color: '#F9F8EF', marginVertical: 5, fontWeight: '500' },
  reviewTotal: { fontSize: 13, lineHeight: 20, fontVariant: ['tabular-nums'], color: '#BED2C8' },
  reviewRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 18, paddingVertical: 13, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#DDE3DA' },
  reviewLabel: { flex: 1, fontSize: 13, lineHeight: 20, color: '#71837D' },
  reviewValue: { flex: 2, fontSize: 14, lineHeight: 20, color: '#274C45', textAlign: 'right', fontVariant: ['tabular-nums'] },
  reviewNote: { fontSize: 12, lineHeight: 18, color: '#7B8A82', textAlign: 'center', marginTop: 20 },
});
