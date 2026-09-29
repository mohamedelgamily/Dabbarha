import { Platform } from 'react-native';

export const colors = {
  // Dabbarha brand palette
  primary: '#02262D',
  primaryDark: '#010D10',
  primaryMuted: '#DCE5E4',
  primaryAccent: '#0D9488',
  primaryVibrant: '#2DD4BF',
  mintSoft: '#F0FDFA',
  mintBorder: '#CCFBF1',

  // Secondary / supporting slate
  secondary: '#71878A',
  secondaryDark: '#4A5B5E',
  secondaryMuted: '#8E9DA0',

  // Neutral / Backgrounds
  background: '#FFFFFF',
  canvas: '#F6F4EF',
  surface: '#FFFFFF',
  surfaceAlt: '#F8FAFC',
  surfaceElevated: '#FFFFFF',

  // Text
  textPrimary: '#010D10',
  textSecondary: '#64748B',
  textMuted: '#94A3B8',
  textInverse: '#FFFFFF',

  // Borders & Dividers
  border: '#E2E8F0',
  borderDark: '#CBD5E1',
  borderSubtle: '#F1F5F9',

  // Feedback states
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

// Shared family and title treatment from New Commitment.
export const typography = {
  fontFamily: Platform.select({
    ios: 'Georgia',
    android: 'serif',
    default: 'serif',
  }),
  title: { fontWeight: '400' as const, letterSpacing: -0.6 },
  sizes: {
    kicker: 11,
    xs: 12,
    sm: 13,
    md: 15,
    lg: 17,
    xl: 20,
    xxl: 24,
    display: 28,
    hero: 34,
  },
  weights: {
    regular: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
    extrabold: '800' as const,
  },
  lineHeights: {
    kicker: 14,
    xs: 16,
    sm: 18,
    md: 22,
    lg: 24,
    xl: 26,
    xxl: 30,
    display: 34,
    hero: 40,
  },
  letterSpacing: {
    tightest: -0.8,
    tighter: -0.5,
    tight: -0.2,
    normal: 0,
    wide: 0.4,
    widest: 0.8,
    kicker: 1.0,
  },
} as const;

export const borderRadius = {
  none: 0,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  full: 9999,
} as const;

export const sizes = {
  inputHeight: 48,
  buttonHeight: 50,
  buttonHeightSm: 38,
  buttonHeightLg: 54,
  touchTarget: 44,
  tabBarHeight: 66,
  iconSm: 16,
  iconMd: 20,
  iconLg: 24,
  logoSymbolSm: 26,
  logoSymbolMd: 36,
  logoSymbolLg: 56,
  logoFullWidth: 170,
} as const;

export const shadows = {
  none: {},
  sm: {
    shadowColor: '#010D10',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  md: {
    shadowColor: '#010D10',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  lg: {
    shadowColor: '#010D10',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
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
