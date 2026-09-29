import { t, translateMessage, isArabic, formatCount } from '@/i18n';
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
import { useAuthStore } from '@/store/authStore';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Button } from '@/components/common/Button';
import { Icon } from '@/components/common/Icon';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { ObligationCard } from '@/components/obligations/ObligationCard';
import { ObligationFormModal } from '@/components/obligations/ObligationFormModal';
import { ObligationDetailModal } from '@/components/obligations/ObligationDetailModal';
import { colors, typography } from '@/constants/theme';
import { formatCurrency } from '@/utils/format';
import Svg, { Defs, LinearGradient, Stop, Rect, Path, G, Circle } from 'react-native-svg';
import { Car, Smartphone, CreditCard, CalendarDays, ArrowRight } from 'lucide-react-native';

const filters = ['All', 'Active', 'Completed', 'Late'] as const;
const getExamples = () => [
  { title: t("Car Loan"), icon: Car },
  { title: t("Phone Installment"), icon: Smartphone },
  { title: t("Credit Card"), icon: CreditCard },
  { title: t("Subscriptions"), icon: CalendarDays },
];

function CommitmentIllustration() {
  return (
    <View style={styles.art} pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Svg width="100%" height="100%" viewBox="0 0 360 205" preserveAspectRatio="xMidYMid slice">
        <Defs>
          <LinearGradient id="mist" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0" stopColor="#387C70" /><Stop offset="0.65" stopColor="#D5DDD0" /><Stop offset="1" stopColor="#F6F4EF" />
          </LinearGradient>
          <LinearGradient id="glass" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0" stopColor="#F6F9ED" stopOpacity="0.95" /><Stop offset="1" stopColor="#A6C8B7" stopOpacity="0.85" />
          </LinearGradient>
        </Defs>
        <Rect width="360" height="205" fill="url(#mist)" />
        <Path d="M-30 125 L199 -25 H288 L-30 182Z" fill="#F6F5DE" opacity="0.12" />
        <Path d="M-20 160 C60 87 195 143 300 15 L400 -30 V205 H-20Z" fill="#F9F7E8" opacity="0.27" />
        <G transform="translate(123 77) rotate(7 57 40)">
          <Rect width="115" height="78" rx="14" fill="#E1E9DB" stroke="#F9FBF0" strokeWidth="1.5" />
        </G>
        <G transform="translate(107 55) rotate(-11 55 44)">
          <Rect y="9" width="108" height="85" rx="14" fill="#315F53" opacity="0.12" />
          <Rect width="108" height="85" rx="14" fill="url(#glass)" stroke="#F9FBF0" strokeWidth="2" />
          <Rect x="18" y="21" width="57" height="11" rx="5" fill="#90B9AA" />
          <Rect x="43" y="48" width="35" height="9" rx="4" fill="#90B9AA" />
        </G>
        <Circle cx="228" cy="150" r="23" fill="#1D554B" opacity="0.12" />
        <Circle cx="228" cy="145" r="21" fill="#034237" />
        <Path d="M220 145 H236 M228 137 V153" stroke="#E7F0DE" strokeWidth="1.6" strokeLinecap="round" />
      </Svg>
    </View>
  );
}

export default function ObligationsScreen() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<(typeof filters)[number]>('All');
  const { user } = useAuthStore();
  const currency = user?.currency || 'EGP';

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
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      queryClient.invalidateQueries({ queryKey: ['forecast'] });
      setSelectedObligation(null);
    },
    onError: (err: any) => {
      Alert.alert(
        t("Deletion Failed"),
        translateMessage(err?.message) || t("Unable to delete obligation. Please try again.")
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
      t("Delete Obligation"),
      t('Are you sure you want to remove "{name}"? This action cannot be undone.', { name: obligation.item_name }),
      [
        { text: t("Cancel"), style: 'cancel' },
        {
          text: t("Delete"),
          style: 'destructive',
          onPress: () => deleteMutation.mutate(obligation.id),
        },
      ]
    );
  };

  const items = obligations || [];
  const filteredItems = filter === 'All' ? items : items.filter((item) => item.status === filter.toLowerCase());
  const activeItems = items.filter((o) => o.status === 'active');
  const totalMonthly = activeItems.reduce(
    (sum, o) => sum + Number(o.monthly_installment_amount || 0),
    0
  );
  const totalPortfolioValue = items.reduce(
    (sum, o) => sum + Number(o.total_amount || 0),
    0
  );

  const renderHeader = () => (
    <>
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <View style={styles.headerCopy}>
            <Typography style={styles.title}>{t("Obligations")}</Typography>
            <Typography style={styles.subtitle}>{t("All your financial commitments")}</Typography>
          </View>
          <TouchableOpacity onPress={handleOpenAdd} style={styles.addButton} accessibilityRole="button" accessibilityLabel={t("Add commitment")}>
            <Icon name="plus" size={24} color={colors.primary} strokeWidth={1.5} />
          </TouchableOpacity>
        </View>
        <View style={styles.filters}>
          {filters.map((label) => (
            <TouchableOpacity key={label} style={[styles.filter, label === filter && styles.filterSelected]}
              onPress={() => setFilter(label)} accessibilityRole="button" accessibilityState={{ selected: label === filter }}>
              <Typography style={[styles.filterText, label === filter && styles.filterTextSelected]}>{translateMessage(label)}</Typography>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      {items.length > 0 && <View style={styles.summary}>
        <View style={styles.summaryCell}>
          <Typography style={styles.summaryLabel}>{t("Monthly total")}</Typography>
          <Typography style={styles.summaryValue} adjustsFontSizeToFit numberOfLines={1}>{formatCurrency(totalMonthly, currency)}</Typography>
        </View>
        <View style={styles.summaryCell}>
          <Typography style={styles.summaryLabel}>{t("Active")}</Typography>
          <Typography style={styles.summaryValue}>{formatCount(activeItems.length)}</Typography>
        </View>
        <View style={styles.summaryCell}>
          <Typography style={styles.summaryLabel}>{t("Total value")}</Typography>
          <Typography style={styles.summaryValue} adjustsFontSizeToFit numberOfLines={1}>{formatCurrency(totalPortfolioValue, currency)}</Typography>
        </View>
      </View>}
    </>
  );
  return (
    <ScreenWrapper backgroundColor={colors.primary} statusBarStyle="light">
      <FlatList
        style={styles.list}
        data={isLoading || isError ? [] : filteredItems}
        keyExtractor={(item) => String(item.id)}
        ListHeaderComponent={renderHeader()}
        renderItem={({ item }) => (
          <View style={styles.item}>
            <ObligationCard obligation={item} currency={currency} onPress={(ob) => setSelectedObligation(ob)} />
          </View>
        )}
        ListEmptyComponent={
          isLoading ? <LoadingIndicator message={t("Loading commitments...")} /> :
          isError ? <View style={styles.state}>
            <ErrorBanner message={(error as any)?.message || t("Failed to load obligations. Please check your connection.")} />
            <Button title={t("Try Again")} onPress={() => refetch()} />
          </View> :
          items.length > 0 ? <View style={styles.filteredEmpty}>
            <Typography style={styles.emptyTitle}>{t('No commitments with status: {status}', { status: translateMessage(filter) })}</Typography>
            <Typography style={styles.emptyText}>{t("Try another filter to view your commitments.")}</Typography>
            <Button title={t("View all commitments")} onPress={() => setFilter('All')} variant="outline" />
          </View> :
          <View style={styles.emptyComposition}>
            <View style={styles.emptyCard}>
              <CommitmentIllustration />
              <View style={styles.emptyCopy}>
                <Typography style={styles.emptyTitle}>{t("No commitments yet")}</Typography>
                <Typography style={styles.emptyText}>{t("Track your loans, installments, subscriptions and fixed expenses to stay in control of your financial future.")}</Typography>
                <TouchableOpacity onPress={handleOpenAdd} style={styles.emptyCta} accessibilityRole="button" accessibilityLabel={t("Add Your First Commitment")}>
                  <Typography style={styles.emptyCtaText}>{t("Add Your First Commitment")}</Typography>
                  <ArrowRight style={isArabic() ? { transform: [{ scaleX: -1 }] } : undefined} size={18} color="#F2F5EA" />
                </TouchableOpacity>
              </View>
            </View>
            <Typography style={styles.examplesTitle}>{t("Popular examples")}</Typography>
            <View style={styles.examples}>
              {getExamples().map(({ title, icon: ExampleIcon }) => (
                <View key={title} style={styles.example}>
                  <View style={styles.exampleIcon}><ExampleIcon size={23} color="#254549" strokeWidth={1.5} /></View>
                  <Typography style={styles.exampleText}>{title}</Typography>
                </View>
              ))}
            </View>
          </View>
        }
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#C1D6C8" colors={[colors.primary]} />}
      />
      <ObligationFormModal visible={formModalVisible} onClose={() => setFormModalVisible(false)}
        initialData={editingObligation} onSuccess={() => {
          if (selectedObligation && editingObligation) setSelectedObligation(null);
        }} />
      <ObligationDetailModal visible={!!selectedObligation} obligation={selectedObligation} currency={currency}
        onClose={() => setSelectedObligation(null)} onEdit={handleOpenEdit} onDelete={handleDeleteConfirm}
        isDeleting={deleteMutation.isPending} />
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  list: { backgroundColor: '#F6F4EF' },
  listContent: { flexGrow: 1, paddingBottom: 25 },
  header: { backgroundColor: '#02262D', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 45 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  headerCopy: { flex: 1 },
  title: { ...typography.title, fontSize: 32, lineHeight: 40, color: '#F8F7EC' },
  subtitle: { fontSize: 13, lineHeight: 19, color: '#B3CBC4', marginTop: 1 },
  addButton: { width: 46, height: 46, borderRadius: 15, backgroundColor: '#EFF6E9', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#D5E5D8' },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 19 },
  filter: { flexGrow: 1, minHeight: 38, paddingHorizontal: 13, paddingVertical: 9, borderRadius: 22, borderWidth: 1, borderColor: '#335955', alignItems: 'center', justifyContent: 'center' },
  filterSelected: { backgroundColor: '#F0F2E7', borderColor: '#F0F2E7' },
  filterText: { fontSize: 12, lineHeight: 17, color: '#C4D6CE' },
  filterTextSelected: { color: '#173D3C', fontWeight: '600' },
  emptyComposition: { marginTop: -24, paddingHorizontal: 14 },
  emptyCard: { borderRadius: 24, overflow: 'hidden', backgroundColor: '#F9F7F1', borderWidth: 1, borderColor: '#E2E9DC' },
  art: { width: '100%', height: 200 },
  emptyCopy: { paddingHorizontal: 22, paddingBottom: 25, paddingTop: 0, alignItems: 'center' },
  emptyTitle: { ...typography.title, fontSize: 23, lineHeight: 30, color: '#183D3C', textAlign: 'center' },
  emptyText: { fontSize: 13, lineHeight: 20, color: '#617B7C', textAlign: 'center', marginTop: 8, marginBottom: 21, maxWidth: 290 },
  emptyCta: { width: '100%', minHeight: 53, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: '#02262D', borderRadius: 12, paddingHorizontal: 13, paddingVertical: 14 },
  emptyCtaText: { fontSize: 14, lineHeight: 20, color: '#F3F6ED', flexShrink: 1, textAlign: 'center' },
  examplesTitle: { ...typography.title, fontSize: 15, lineHeight: 22, color: '#294849', marginTop: 24, marginBottom: 12, marginStart: 2 },
  examples: { flexDirection: 'row', gap: 12 },
  example: { flex: 1, minWidth: 0, alignItems: 'center' },
  exampleIcon: { width: '100%', minHeight: 65, borderRadius: 16, backgroundColor: '#FBFAF5', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#EBECE4' },
  exampleText: { fontSize: 11, lineHeight: 16, color: '#617476', textAlign: 'center', marginTop: 7 },
  summary: { marginHorizontal: 16, marginTop: -22, marginBottom: 19, paddingVertical: 16, paddingHorizontal: 10, borderRadius: 18, borderWidth: 1, borderColor: '#DCE4DB', backgroundColor: '#F4F6EC', flexDirection: 'row', gap: 10 },
  summaryCell: { flex: 1, minWidth: 0 },
  summaryLabel: { fontSize: 10, lineHeight: 15, color: '#6B807A', marginBottom: 4 },
  summaryValue: { fontSize: 13, lineHeight: 20, color: '#254C45', fontVariant: ['tabular-nums'] },
  item: { paddingHorizontal: 16 },
  filteredEmpty: { padding: 25, alignItems: 'center' },
  state: { padding: 22 },
});