import React, { useEffect } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity, I18nManager } from 'react-native';
import { reloadAppAsync } from 'expo';
import { useFonts } from 'expo-font';
import { useLanguageStore } from '@/store/languageStore';
import { t } from '@/i18n';

// Recovery must stay readable even when bundled fonts failed to load.
const recoveryText = { textAlign: 'center' as const, fontSize: 16, lineHeight: 28, color: '#02262D' };

export function LocalizationProvider({ children }: { children: React.ReactNode }) {
  const { ready, initialize, error, busy, select } = useLanguageStore();
  const [fontsLoaded, fontError] = useFonts({
    NotoNaskhArabic: require('../../assets/fonts/NotoNaskhArabic-Regular.ttf'),
    NotoNaskhArabicBold: require('../../assets/fonts/NotoNaskhArabic-Bold.ttf'),
  });
  useEffect(() => { void initialize(); }, [initialize]);
  if (!ready || !fontsLoaded) {
    const message = fontError ? t('Could not load fonts. Please try again.')
      : error === 'restart' ? t('Please close and reopen Dabbarha to apply the layout direction.')
      : error === 'expoGo' ? t('RTL switching requires a development or installed build. Expo Go cannot reliably apply it.')
      : error === 'load' ? t('Could not load language settings. Please try again.') : null;
    return <View style={{ flex: 1, justifyContent: 'center', padding: 28, backgroundColor: '#F6F4EF', gap: 20 }}>
      {message ? <>
        <Text style={recoveryText} accessibilityLiveRegion="polite">{message}</Text>
        {error === 'load' && <TouchableOpacity onPress={() => { void initialize(); }} disabled={busy} accessibilityRole="button" style={{ padding: 16 }}><Text style={recoveryText}>{t('Retry')}</Text></TouchableOpacity>}
        {fontError && <TouchableOpacity accessibilityRole="button" onPress={() => { void reloadAppAsync('Retry font loading').catch(() => undefined); }} style={{ padding: 16 }}><Text style={recoveryText}>{t('Retry')}</Text></TouchableOpacity>}
        {(error === 'expoGo' || error === 'restart') && <TouchableOpacity accessibilityRole="button" onPress={() => { void select(I18nManager.isRTL ? 'ar' : 'en'); }} style={{ padding: 16 }}><Text style={recoveryText}>{I18nManager.isRTL ? 'العربية' : 'English'}</Text></TouchableOpacity>}
      </> : <ActivityIndicator color="#02262D" accessibilityLabel={t('Loading Dabbarha...')} />}
    </View>;
  }
  return <>{children}</>;
}
