import React, { useEffect } from 'react';
import { Stack, useRouter, useSegments } from 'expo-router';
import { QueryProvider } from '@/providers/QueryProvider';
import { useAuthStore } from '@/store/authStore';
import { LoadingIndicator } from '@/components/common/LoadingIndicator';
import { colors } from '@/constants/theme';

function RootNavigationLayout() {
  const { isAuthenticated, isInitialized, initializeAuth } = useAuthStore();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  useEffect(() => {
    if (!isInitialized) return;

    const inAuthGroup = segments[0] === '(auth)';

    if (!isAuthenticated && !inAuthGroup) {
      // Redirect unauthenticated user to login screen
      router.replace('/(auth)/login');
    } else if (isAuthenticated && inAuthGroup) {
      // Redirect authenticated user to main app tabs
      router.replace('/(tabs)');
    }
  }, [isAuthenticated, isInitialized, segments, router]);

  if (!isInitialized) {
    return <LoadingIndicator message="Loading Dabbarha..." />;
  }

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="(auth)" options={{ headerShown: false }} />
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="+not-found" options={{ title: 'Oops!' }} />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <QueryProvider>
      <RootNavigationLayout />
    </QueryProvider>
  );
}
