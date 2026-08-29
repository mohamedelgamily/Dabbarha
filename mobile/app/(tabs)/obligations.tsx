import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ScreenWrapper } from '@/components/common/ScreenWrapper';
import { Typography } from '@/components/common/Typography';
import { Card } from '@/components/common/Card';
import { colors, spacing } from '@/constants/theme';

export default function ObligationsPlaceholderScreen() {
  return (
    <ScreenWrapper scrollable>
      <View style={styles.header}>
        <Typography variant="h1">
          Obligations
        </Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.subtitle}>
          Track loans, installments & financial commitments
        </Typography>
      </View>

      <Card style={styles.card}>
        <Typography variant="h3" color={colors.primary}>
          Obligations Service Configured
        </Typography>
        <Typography variant="body" color={colors.textSecondary} style={styles.cardText}>
          The CRUD API service for obligations is modeled and ready for integration in upcoming phases.
        </Typography>
      </Card>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  header: {
    marginVertical: spacing.md,
  },
  subtitle: {
    marginTop: spacing.xs,
  },
  card: {
    marginTop: spacing.md,
  },
  cardText: {
    marginTop: spacing.sm,
    lineHeight: 22,
  },
});
