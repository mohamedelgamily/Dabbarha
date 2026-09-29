import React, { useEffect, useId } from 'react';
import { Alert, StyleSheet, View, TouchableOpacity } from 'react-native';
import { useLanguageStore } from '@/store/languageStore';
import { t } from '@/i18n';
import type { Language } from '@/i18n/dictionaries';
import { Typography } from './Typography';
import { colors } from '@/constants/theme';

export function LanguageSelector({ dirty = false, disabled = false }: { dirty?: boolean; disabled?: boolean }) {
  const { language, select, busy, error, chatProtected } = useLanguageStore();
  const formId = useId();
  useEffect(() => {
    useLanguageStore.getState().setFormDirty(formId, dirty);
    return () => useLanguageStore.getState().setFormDirty(formId, false);
  }, [formId, dirty]);
  const choose = (next: Language) => {
    if (next === language || disabled || busy || chatProtected) return;
    Alert.alert(t('Change language'), t('The app will restart to apply the language and layout.') +
      (dirty || Object.keys(useLanguageStore.getState().dirtyForms).length > 0 ? '\n\n' + t('Unsaved changes will be lost. Continue?') : ''), [
      { text: t('Cancel'), style: 'cancel' },
      { text: t('Restart and change language'), onPress: () => { void select(next).then(() => {
        if (useLanguageStore.getState().error === 'expoGo') {
          Alert.alert(t('Change language'), t('RTL switching requires a development or installed build. Expo Go cannot reliably apply it.'));
        }
      }); } },
    ]);
  };
  return <View style={styles.container}>
    <Typography variant="label">{t('Language')}</Typography>
    <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t('Language')}>
      {(['en', 'ar'] as const).map(value => <TouchableOpacity key={value}
        onPress={() => choose(value)} disabled={disabled || busy || chatProtected} accessibilityRole="radio"
        accessibilityLabel={value === 'ar' ? 'العربية' : 'English'}
        accessibilityState={{ checked: language === value, disabled: disabled || busy || chatProtected }}
        style={[styles.choice, language === value && styles.selected]}>
        <Typography style={[styles.label, value === 'ar' && { fontFamily: 'NotoNaskhArabic' }, language === value && styles.selectedLabel]}>
          {value === 'ar' ? 'العربية' : 'English'}
        </Typography>
      </TouchableOpacity>)}
    </View>
    {chatProtected && <Typography variant="caption">{t('Finish or cancel the pending chat action before leaving or changing language.')}</Typography>}
    {error === 'save' && <Typography variant="error" accessibilityLiveRegion="polite">{t('Could not save your language. Please try again.')}</Typography>}
  </View>;
}
const styles = StyleSheet.create({
  container: { gap: 8, marginVertical: 16 },
  choices: { flexDirection: 'row', gap: 8 },
  choice: { minHeight: 44, flex: 1, justifyContent: 'center', alignItems: 'center', borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: '#FBFAF5', padding: 8 },
  selected: { backgroundColor: colors.primary, borderColor: colors.primary },
  label: { textAlign: 'center', fontSize: 15, lineHeight: 26, color: colors.primary },
  selectedLabel: { color: '#F1F5E7' },
});
