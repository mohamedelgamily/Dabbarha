import React from 'react';
import {
  TouchableOpacity,
  View,
  StyleSheet,
  StyleProp,
  ViewStyle,
} from 'react-native';
import { colors, spacing } from '@/constants/theme';
import { Typography } from './Typography';
import { Icon, IconName } from './Icon';

interface ListRowProps {
  icon?: IconName;
  title: string;
  subtitle?: string;
  trailing?: string;
  showChevron?: boolean;
  onPress?: () => void;
  destructive?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function ListRow({
  icon,
  title,
  subtitle,
  trailing,
  showChevron = true,
  onPress,
  destructive = false,
  style,
}: ListRowProps) {
  const titleColor = destructive ? colors.error : colors.textPrimary;
  const Wrap: React.ElementType = onPress ? TouchableOpacity : View;
  const wrapProps = onPress ? { onPress, activeOpacity: 0.7 } : {};

  return (
    <Wrap
      {...wrapProps}
      style={[styles.row, style]}
      accessibilityRole={onPress ? 'button' : undefined}
    >
      {icon ? (
        <View style={styles.iconWrap}>
          <Icon name={icon} size={20} tone={destructive ? 'error' : 'primary'} />
        </View>
      ) : null}
      <View style={styles.textCol}>
        <Typography variant="bodyBold" style={{ color: titleColor }} numberOfLines={1}>
          {title}
        </Typography>
        {subtitle ? (
          <Typography
            variant="caption"
            color={colors.textSecondary}
            style={styles.subtitle}
            numberOfLines={1}
          >
            {subtitle}
          </Typography>
        ) : null}
      </View>
      {trailing ? (
        <Typography variant="body" color={colors.textSecondary} style={styles.trailing}>
          {trailing}
        </Typography>
      ) : null}
      {showChevron && onPress ? (
        <Icon name="chevron-right" size={18} tone="muted" />
      ) : null}
    </Wrap>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    minHeight: 56,
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  textCol: {
    flex: 1,
  },
  subtitle: {
    marginTop: 2,
  },
  trailing: {
    marginRight: spacing.sm,
  },
});
