export const colors = {
  // Dabbarha brand palette
  primary: '#02262D',
  primaryDark: '#010D10',
  primaryMuted: '#DCE5E4',

  // Secondary / supporting
  secondary: '#71878A',

  // Neutral / Backgrounds
  background: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceAlt: '#DCE5E4',

  // Text
  textPrimary: '#010D10',
  textSecondary: '#71878A',
  textMuted: '#9AA7A9',
  textInverse: '#FFFFFF',

  // Borders & Dividers
  border: '#E4E7E7',
  borderDark: '#C9D0D0',

  // Feedback states (semantically distinct from brand)
  success: '#10B981',
  successLight: '#D1FAE5',
  warning: '#D97706',
  warningLight: '#FEF3C7',
  error: '#DC2626',
  errorLight: '#FEE2E2',
  info: '#0EA5E9',
  infoLight: '#E0F2FE',
} as const;

export const spacing = {
  none: 0,
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const typography = {
  sizes: {
    xs: 12,
    sm: 14,
    md: 16,
    lg: 18,
    xl: 20,
    xxl: 24,
    hero: 32,
  },
  weights: {
    regular: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
  },
  lineHeights: {
    xs: 16,
    sm: 20,
    md: 24,
    lg: 28,
    xl: 28,
    xxl: 32,
    hero: 40,
  },
} as const;

export const borderRadius = {
  none: 0,
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  full: 9999,
} as const;

export const sizes = {
  inputHeight: 48,
  buttonHeight: 52,
  buttonHeightSm: 40,
  buttonHeightLg: 56,
  touchTarget: 44,
  tabBarHeight: 64,
  iconSm: 16,
  iconMd: 20,
  iconLg: 24,
  logoSymbolSm: 28,
  logoSymbolMd: 40,
  logoSymbolLg: 64,
  logoFullWidth: 180,
} as const;

export const shadows = {
  none: {},
  sm: {
    shadowColor: '#010D10',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  md: {
    shadowColor: '#010D10',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
} as const;

export const theme = {
  colors,
  spacing,
  typography,
  borderRadius,
  sizes,
  shadows,
};

export type Theme = typeof theme;
