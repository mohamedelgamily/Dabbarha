import React from 'react';
import { View, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { colors, spacing } from '@/constants/theme';
import { Typography } from './Typography';
import { IconButton } from './IconButton';
import { IconName } from './Icon';

interface ScreenHeaderProps {
  title: string;
  subtitle?: string;
  rightIcon?: IconName;
  onRightPress?: () => void;
  rightLabel?: string;
  rightAccessibilityLabel?: string;
  onRightLabelPress?: () => void;
  style?: StyleProp<ViewStyle>;
}

export function ScreenHeader({
  title,
  subtitle,
  rightIcon,
  onRightPress,
  rightLabel,
  rightAccessibilityLabel,
  onRightLabelPress,
  style,
}: ScreenHeaderProps) {
  const hasRight = !!rightIcon || !!rightLabel;
  return (
    <View style={[styles.container, style]}>
      <View style={styles.textCol}>
        <Typography variant="h1" numberOfLines={1}>
          {title}
        </Typography>
        {subtitle ? (
          <Typography
            variant="body"
            color={colors.textSecondary}
            style={styles.subtitle}
            numberOfLines={2}
          >
            {subtitle}
          </Typography>
        ) : null}
      </View>
      {hasRight ? (
        <View style={styles.end}>
          {rightLabel ? (
            <Typography
              variant="bodyBold"
              color={colors.primary}
              onPress={onRightLabelPress}
              style={styles.rightLabel}
            >
              {rightLabel}
            </Typography>
          ) : null}
          {rightIcon && onRightPress ? (
            <IconButton
              name={rightIcon}
              variant="soft"
              onPress={onRightPress}
              accessibilityLabel={rightAccessibilityLabel || rightLabel}
            />
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
  },
  textCol: {
    flex: 1,
    marginEnd: spacing.md,
  },
  subtitle: {
    marginTop: spacing.xs / 2,
  },
  end: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  rightLabel: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.xs,
  },
});
