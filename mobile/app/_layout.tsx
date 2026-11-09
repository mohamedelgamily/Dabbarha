import { t } from '@/i18n';
import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { QueryProvider } from '@/providers/QueryProvider';
import { useAuthStore } from '@/store/authStore';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { colors } from '@/constants/theme';
import { LocalizationProvider } from '@/providers/LocalizationProvider';

function RootNavigationLayout() {
  const { isAuthenticated, isInitialized, initializeAuth, sessionId } = useAuthStore();

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  if (!isInitialized) {
    return <LoadingIndicator message={t("Loading Dabbarha...")} color={colors.primary} />;
  }

  return (
    <Stack
      key={isAuthenticated ? sessionId : 'signed-out'}
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Protected guard={!isAuthenticated}>
        <Stack.Screen name="(auth)" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={isAuthenticated}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="affordability" />
      </Stack.Protected>
      <Stack.Protected guard={false}>
        <Stack.Screen name="chat" />
      </Stack.Protected>
      <Stack.Screen name="+not-found" options={{ title: t("Oops!") }} />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <LocalizationProvider>
      <QueryProvider>
        <RootNavigationLayout />
      </QueryProvider>
    </LocalizationProvider>
  );
}
