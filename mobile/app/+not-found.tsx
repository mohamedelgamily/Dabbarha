import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Link, Stack } from 'expo-router';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { colors, spacing } from '@/constants/theme';

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Page Not Found', headerShown: true }} />
      <ScreenWrapper>
        <View style={styles.container}>
          <Typography variant="h1" align="center">
            404
          </Typography>
          <Typography variant="body" color={colors.textSecondary} align="center" style={styles.message}>
            This screen doesn't exist.
          </Typography>
          <Link href="/" asChild style={styles.link}>
            <Typography variant="bodyBold" color={colors.primary} align="center">
              Go to Home screen
            </Typography>
          </Link>
        </View>
      </ScreenWrapper>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  message: {
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
  },
  link: {
    paddingVertical: spacing.md,
  },
});
