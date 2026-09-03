import React from 'react';
import {
  TouchableOpacity,
  View,
  StyleSheet,
  StyleProp,
  ViewStyle,
} from 'react-native';
import { colors, spacing, borderRadius } from '@/constants/theme';
import { Typography } from './Typography';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

interface SegmentedProps<T extends string> {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  fullWidth?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  fullWidth = true,
  style,
}: SegmentedProps<T>) {
  return (
    <View style={[styles.track, fullWidth && styles.fullWidth, style]}>
      {options.map((opt) => {
        const selected = opt.value === value;
        return (
          <TouchableOpacity
            key={opt.value}
            onPress={() => !opt.disabled && onChange(opt.value)}
            disabled={opt.disabled}
            activeOpacity={0.7}
            style={[
              styles.segment,
              fullWidth && styles.segmentFlex,
              selected && styles.segmentSelected,
            ]}
            accessibilityRole="button"
            accessibilityState={{ selected, disabled: opt.disabled }}
          >
            <Typography
              variant="label"
              style={[
                styles.label,
                selected && styles.labelSelected,
                opt.disabled && styles.labelDisabled,
              ]}
            >
              {opt.label}
            </Typography>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceAlt,
    borderRadius: borderRadius.full,
    padding: 4,
    gap: 4,
  },
  fullWidth: {
    alignSelf: 'stretch',
  },
  segment: {
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentFlex: {
    flex: 1,
  },
  segmentSelected: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  label: {
    color: colors.textSecondary,
  },
  labelSelected: {
    color: colors.primary,
    fontWeight: '600',
  },
  labelDisabled: {
    opacity: 0.5,
  },
});
