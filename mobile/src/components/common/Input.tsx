import { t } from '@/i18n';
import React, { useState } from 'react';
import {
  View,
  TextInput,
  StyleSheet,
  TextInputProps,
  ViewStyle,
  TouchableOpacity,
  StyleProp,
} from 'react-native';
import { colors, spacing, borderRadius, typography } from '@/constants/theme';
import { Typography } from './Typography';
import { isArabic, normalizeNumericInput, translateMessage } from '@/i18n';

interface InputProps extends TextInputProps {
  label?: string;
  error?: string;
  helperText?: string;
  containerStyle?: StyleProp<ViewStyle>;
  isPassword?: boolean;
  numeric?: boolean;
  dateInput?: boolean;
}

export function Input({
  label,
  error,
  helperText,
  containerStyle,
  isPassword = false,
  numeric = false,
  dateInput = false,
  style,
  ...props
}: InputProps) {
  const [isFocused, setIsFocused] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const isNumeric = numeric || props.keyboardType === 'decimal-pad' || props.keyboardType === 'number-pad' || props.keyboardType === 'numeric';
  const ltr = isNumeric || dateInput || isPassword || props.keyboardType === 'email-address';

  return (
    <View style={[styles.container, containerStyle]}>
      {label ? (
        <Typography variant="label" style={styles.label}>
          {label}
        </Typography>
      ) : null}

      <View
        style={[
          styles.inputWrapper,
          isFocused && styles.focused,
          !!error && styles.errorBorder,
        ]}
      >
        <TextInput
          style={[styles.input, style, { textAlign: 'left', direction: ltr ? 'ltr' : isArabic() ? 'rtl' : 'ltr', writingDirection: ltr ? 'ltr' : 'auto' }, isArabic() && !ltr && { fontFamily: 'NotoNaskhArabic', lineHeight: 27 }]}
          placeholderTextColor={colors.textMuted}
          secureTextEntry={isPassword && !showPassword}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          {...props}
          accessibilityLabel={props.accessibilityLabel || label}
          onChangeText={(value) => props.onChangeText?.(isNumeric || dateInput ? normalizeNumericInput(value) : value)}
        />
        {isPassword ? (
          <TouchableOpacity
            style={styles.toggleButton}
            onPress={() => setShowPassword((prev) => !prev)}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel={showPassword ? t('Hide') : t('Show')}
          >
            <Typography variant="caption" color={colors.primary}>
              {showPassword ? t("Hide") : t("Show")}
            </Typography>
          </TouchableOpacity>
        ) : null}
      </View>

      {error ? (
        <Typography variant="error" style={styles.errorText}>
          {translateMessage(error)}
        </Typography>
      ) : helperText ? (
        <Typography variant="caption" style={styles.helperText}>
          {helperText}
        </Typography>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: spacing.md,
  },
  label: {
    marginBottom: spacing.xs,
    color: colors.textPrimary,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
  },
  input: {
    fontFamily: typography.fontFamily,
    flex: 1,
    paddingVertical: spacing.sm + 4,
    fontSize: typography.sizes.md,
    color: colors.textPrimary,
  },
  focused: {
    borderColor: colors.primary,
    borderWidth: 1.5,
  },
  errorBorder: {
    borderColor: colors.error,
    borderWidth: 1.5,
  },
  toggleButton: {
    paddingStart: spacing.sm,
  },
  errorText: {
    marginTop: spacing.xs,
  },
  helperText: {
    marginTop: spacing.xs,
    color: colors.textSecondary,
  },
});
