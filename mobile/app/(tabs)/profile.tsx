import React, { useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { Icon } from '@/components/common/Icon';
import { useAuthStore } from '@/store/authStore';
import { colors, typography } from '@/constants/theme';
import { formatCurrency } from '@/utils/format';

const CURRENCIES = ['EGP', 'USD', 'SAR', 'AED', 'EUR'];

export default function ProfileScreen() {
  const queryClient = useQueryClient();
  const { user, logout, isLoading, error, clearError, updateProfile } =
    useAuthStore();

  const [monthlyIncome, setMonthlyIncome] = useState('');
  const [fixedExpenses, setFixedExpenses] = useState('');
  const [currency, setCurrency] = useState('EGP');
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (user) {
      setMonthlyIncome(
        user.monthly_income != null && String(user.monthly_income) !== '0'
          ? String(user.monthly_income)
          : ''
      );
      setFixedExpenses(
        user.fixed_expenses != null && String(user.fixed_expenses) !== '0'
          ? String(user.fixed_expenses)
          : ''
      );
      setCurrency(user.currency || 'EGP');
    }
  }, [user]);

  const incomeError = monthlyIncome.trim() !== '' && (!Number.isFinite(Number(monthlyIncome)) || Number(monthlyIncome) < 0)
    ? 'Enter a valid amount of zero or more.' : undefined;
  const expensesError = fixedExpenses.trim() !== '' && (!Number.isFinite(Number(fixedExpenses)) || Number(fixedExpenses) < 0)
    ? 'Enter a valid amount of zero or more.' : undefined;
  const handleSave = async () => {
    if (isSaving || incomeError || expensesError) return;
    setSaveError(null);
    setSaveSuccess(false);
    setIsSaving(true);
    try {
      await updateProfile({
        monthly_income:
          monthlyIncome.trim() === '' ? undefined : Number(monthlyIncome),
        fixed_expenses:
          fixedExpenses.trim() === '' ? undefined : Number(fixedExpenses),
        currency: currency.trim() || 'EGP',
      });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      queryClient.invalidateQueries({ queryKey: ['forecast'] });
      setSaveSuccess(true);
      setIsEditing(false);
      setTimeout(() => setSaveSuccess(false), 4000);
    } catch (err) {
      setSaveError((err as { message?: string })?.message || 'Failed to update profile. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSignOutConfirm = () => {
    Alert.alert(
      'Sign Out',
      'Are you sure you want to sign out of your Dabbarha account?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out',
          style: 'destructive',
          onPress: () => logout(),
        },
      ]
    );
  };

  const userInitial = user?.name ? user.name.trim().charAt(0).toUpperCase() : 'U';

  const savedCurrency = user?.currency || 'EGP';
  const hasIncome = Number(user?.monthly_income || 0) > 0;
  const hasExpenses = Number(user?.fixed_expenses || 0) > 0;
  const currencyOptions = Array.from(new Set([...CURRENCIES, savedCurrency]));
  const beginEdit = () => {
    if (isEditing || isSaving) return;
    setMonthlyIncome(Number(user?.monthly_income || 0) === 0 ? '' : String(user?.monthly_income));
    setFixedExpenses(Number(user?.fixed_expenses || 0) === 0 ? '' : String(user?.fixed_expenses));
    setCurrency(savedCurrency);
    setSaveError(null);
    setSaveSuccess(false);
    clearError();
    setIsEditing(true);
  };
  const cancelEdit = () => {
    setIsEditing(false);
    setSaveError(null);
    clearError();
    setCurrency(savedCurrency);
  };

  return (
    <ScreenWrapper backgroundColor={colors.primary} statusBarStyle="light">
      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
        <View style={styles.hero}>
          <Typography style={styles.pageTitle}>Profile</Typography>
          <Typography style={styles.subtitle}>Your account & financial settings</Typography>
          <View style={styles.identityCard}>
            <View style={styles.avatar}><Typography style={styles.initial}>{userInitial || 'U'}</Typography></View>
            <View style={styles.identityCopy}>
              <Typography style={styles.userName}>{user?.name || 'Your account'}</Typography>
              {user?.email && <Typography style={styles.email} selectable>{user.email}</Typography>}
            </View>
          </View>
        </View>
        <View style={styles.lower}>
          <TouchableOpacity style={[styles.setupCard, hasIncome && styles.configuredCard]} onPress={beginEdit}
            disabled={isSaving} activeOpacity={0.85} accessibilityRole="button" accessibilityLabel={hasIncome ? 'Review financial profile' : 'Continue financial profile setup'}>
            <View pointerEvents="none" style={styles.setupArc} />
            <View style={styles.setupTop}>
              <View style={styles.setupIcon}><Icon name={hasIncome ? 'check-circle' : 'trending-up'} size={28} color="#D6C698" strokeWidth={1.3} /></View>
              <View style={styles.setupCopy}>
                <Typography style={styles.setupTitle}>{hasIncome ? 'Your financial baseline is set' : 'Build a smarter you'}</Typography>
                <Typography style={styles.setupBody}>{hasIncome
                  ? 'Keep your income and recurring expenses up to date as your finances change.'
                  : 'Add optional financial details for more accurate forecasts and affordability insights.'}</Typography>
              </View>
              <Icon name="chevron-right" size={17} color="#DAD4B6" />
            </View>
            <View style={styles.setupCta}><Typography style={styles.setupCtaText}>{hasIncome ? 'Review Financial Profile' : 'Continue Setup'}</Typography><Icon name="chevron-right" size={16} color="#524F35" /></View>
          </TouchableOpacity>

          <View style={styles.sectionHeader}>
            <Typography style={styles.sectionTitle}>Financial Baseline</Typography>
            {!isEditing && <TouchableOpacity onPress={beginEdit} style={styles.editAction} accessibilityRole="button"><Typography style={styles.editText}>Edit</Typography></TouchableOpacity>}
          </View>
          <ErrorBanner message={saveError || error} onDismiss={() => { setSaveError(null); clearError(); }} />
          {saveSuccess && <View style={styles.success}><Icon name="check-circle" size={17} color="#3C7860" /><Typography style={styles.successText} accessibilityLiveRegion="polite">Financial profile updated successfully.</Typography></View>}

          {isEditing ? <View style={styles.editor}>
            <Typography style={styles.editorNote}>Financial details are optional. Leave an amount blank to keep its saved value.</Typography>
            <Input label={'Monthly Net Income · ' + currency} value={monthlyIncome} onChangeText={(value) => { setMonthlyIncome(value); setSaveError(null); }}
              keyboardType="decimal-pad" placeholder="Not set" error={incomeError} editable={!isSaving}
              style={styles.numericInput} helperText="Expected monthly revenue after deductions" />
            <Input label={'Fixed Monthly Expenses · ' + currency} value={fixedExpenses} onChangeText={(value) => { setFixedExpenses(value); setSaveError(null); }}
              keyboardType="decimal-pad" placeholder="Not set" error={expensesError} editable={!isSaving}
              style={styles.numericInput} helperText="Rent, utilities, subscriptions and recurring overhead" />
          </View> : <View>
            <TouchableOpacity onPress={beginEdit} style={styles.financialRow} accessibilityRole="button" accessibilityLabel="Edit monthly net income">
              <View style={styles.rowIcon}><Icon name="wallet" size={22} color="#43776B" strokeWidth={1.5} /></View>
              <View style={styles.rowCopy}>
                <Typography style={styles.rowLabel}>Monthly Net Income</Typography>
                <Typography style={styles.rowValue}>{hasIncome ? formatCurrency(user?.monthly_income, savedCurrency) : 'Not set'}</Typography>
                <Typography style={styles.rowHint}>Expected monthly revenue after deductions</Typography>
              </View>
              <Icon name="chevron-right" size={17} color="#719087" />
            </TouchableOpacity>
            <TouchableOpacity onPress={beginEdit} style={styles.financialRow} accessibilityRole="button" accessibilityLabel="Edit fixed monthly expenses">
              <View style={styles.rowIcon}><Icon name="home" size={22} color="#43776B" strokeWidth={1.5} /></View>
              <View style={styles.rowCopy}>
                <Typography style={styles.rowLabel}>Fixed Monthly Expenses</Typography>
                <Typography style={styles.rowValue}>{hasIncome || hasExpenses ? formatCurrency(user?.fixed_expenses, savedCurrency) : 'Not set'}</Typography>
                <Typography style={styles.rowHint}>Rent, utilities, subscriptions and recurring overhead</Typography>
              </View>
              <Icon name="chevron-right" size={17} color="#719087" />
            </TouchableOpacity>
          </View>}

          <Typography style={styles.currencyLabel}>Primary Currency</Typography>
          <View style={styles.currencies}>
            {currencyOptions.map((option) => {
              const selected = (isEditing ? currency : savedCurrency) === option;
              return <TouchableOpacity key={option} disabled={isSaving} onPress={() => { beginEdit(); setCurrency(option); }}
                style={[styles.currencyChip, selected && styles.currencySelected]} accessibilityRole="radio" accessibilityState={{ checked: selected, disabled: isSaving }}>
                <Typography style={[styles.currencyText, selected && styles.currencyTextSelected]}>{option}</Typography>
              </TouchableOpacity>;
            })}
          </View>
          {isEditing && <>
            <Typography style={styles.currencyNote}>Changing currency updates the label; amounts are not converted.</Typography>
            <View style={styles.editorActions}>
              <TouchableOpacity onPress={cancelEdit} disabled={isSaving} style={styles.cancel} accessibilityRole="button"><Typography style={styles.editText}>Cancel</Typography></TouchableOpacity>
              <Button title="Save Financial Profile" onPress={handleSave} isLoading={isSaving || isLoading}
                disabled={!!incomeError || !!expensesError || !user} style={styles.saveButton} />
            </View>
          </>}
          <TouchableOpacity onPress={handleSignOutConfirm} disabled={isSaving} style={styles.signOut} accessibilityRole="button">
            <Icon name="logout" size={18} color="#A46D5B" /><Typography style={styles.signOutText}>Sign out</Typography>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  scroll: { backgroundColor: '#F6F4EF' },
  scrollContent: { flexGrow: 1, paddingBottom: 28 },
  hero: { backgroundColor: '#02262D', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 40 },
  pageTitle: { ...typography.title, fontSize: 32, lineHeight: 40, color: '#F5F6EA' },
  subtitle: { fontSize: 12, lineHeight: 18, color: '#B9CCC1', marginBottom: 18 },
  identityCard: { flexDirection: 'row', alignItems: 'center', gap: 16, backgroundColor: '#173D3B', padding: 17, borderRadius: 21, borderWidth: 1, borderColor: '#648071' },
  avatar: { width: 62, height: 62, borderRadius: 31, borderWidth: 2, borderColor: '#3B9F89', backgroundColor: '#06433E', alignItems: 'center', justifyContent: 'center' },
  initial: { ...typography.title, fontSize: 27, lineHeight: 34, color: '#D5E9D7' },
  identityCopy: { flex: 1, minWidth: 0 },
  userName: { ...typography.title, fontSize: 18, lineHeight: 25, color: '#F4F5E9' },
  email: { fontSize: 12, lineHeight: 19, color: '#B8CAC0', marginTop: 3 },
  lower: { paddingHorizontal: 16 },
  setupCard: { marginTop: -24, backgroundColor: '#656349', borderRadius: 22, padding: 17, overflow: 'hidden', borderWidth: 1, borderColor: '#A49E7D', marginBottom: 17 },
  configuredCard: { backgroundColor: '#3A5C4F', borderColor: '#77977D' },
  setupArc: { position: 'absolute', width: 190, height: 190, borderRadius: 95, borderWidth: 1, borderColor: 'rgba(236,223,175,0.23)', right: -30, top: -88, transform: [{ scaleX: 1.7 }, { rotate: '-35deg' }] },
  setupTop: { flexDirection: 'row', gap: 11, alignItems: 'flex-start' },
  setupIcon: { width: 36, paddingTop: 5 },
  setupCopy: { flex: 1, minWidth: 0 },
  setupTitle: { ...typography.title, fontSize: 18, lineHeight: 25, color: '#F6F1D9' },
  setupBody: { fontSize: 12, lineHeight: 18, color: '#E0DDC5', marginTop: 4 },
  setupCta: { marginTop: 15, backgroundColor: '#DED2A6', borderRadius: 18, minHeight: 38, paddingVertical: 8, paddingHorizontal: 13, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  setupCtaText: { fontSize: 12, lineHeight: 18, color: '#424A35', flexShrink: 1 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 8 },
  sectionTitle: { ...typography.title, fontSize: 21, lineHeight: 28, color: '#254540', flexShrink: 1 },
  editAction: { minHeight: 44, minWidth: 44, alignItems: 'center', justifyContent: 'center' },
  editText: { fontSize: 13, lineHeight: 20, color: '#3C7163' },
  financialRow: { flexDirection: 'row', alignItems: 'center', gap: 13, backgroundColor: '#FCFBF7', borderWidth: 1, borderColor: '#ECEDE5', borderRadius: 18, padding: 15, marginBottom: 9 },
  rowIcon: { width: 44, height: 44, borderRadius: 15, backgroundColor: '#E0EFE5', alignItems: 'center', justifyContent: 'center' },
  rowCopy: { flex: 1, minWidth: 0 },
  rowLabel: { fontSize: 12, lineHeight: 18, color: '#3B5550' },
  rowValue: { ...typography.title, fontSize: 19, lineHeight: 26, color: '#183F36', fontVariant: ['tabular-nums'] },
  rowHint: { fontSize: 11, lineHeight: 16, color: '#7F9085', marginTop: 2 },
  currencyLabel: { fontSize: 13, lineHeight: 20, color: '#39574D', marginTop: 13, marginBottom: 8 },
  currencies: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  currencyChip: { flexGrow: 1, minWidth: 48, minHeight: 44, paddingHorizontal: 9, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', borderRadius: 11, borderWidth: 1, borderColor: '#E5E8DF', backgroundColor: '#FBFAF5' },
  currencySelected: { backgroundColor: '#02262D', borderColor: '#164A41' },
  currencyText: { fontSize: 12, lineHeight: 18, color: '#71867A' },
  currencyTextSelected: { color: '#F1F5E7' },
  currencyNote: { fontSize: 12, lineHeight: 18, color: '#798A7E', marginTop: 10 },
  editor: { backgroundColor: '#FBFAF5', borderRadius: 18, padding: 16 },
  editorNote: { fontSize: 12, lineHeight: 18, color: '#7A897D', marginBottom: 14 },
  numericInput: { fontVariant: ['tabular-nums'] },
  editorActions: { flexDirection: 'row', gap: 12, alignItems: 'center', marginTop: 15 },
  cancel: { minHeight: 48, paddingHorizontal: 10, justifyContent: 'center' },
  saveButton: { flex: 1, minHeight: 50 },
  success: { flexDirection: 'row', gap: 8, alignItems: 'center', padding: 12, borderRadius: 12, backgroundColor: '#E2EFE3', marginBottom: 12 },
  successText: { fontSize: 12, lineHeight: 18, color: '#3C7257', flex: 1 },
  signOut: { marginTop: 25, paddingVertical: 16, flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'center', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E0E5D9' },
  signOutText: { fontSize: 14, lineHeight: 21, color: '#986855' },
});