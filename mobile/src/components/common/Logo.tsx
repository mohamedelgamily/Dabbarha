import React from 'react';
import { StyleSheet, StyleProp, ViewStyle } from 'react-native';

import SymbolDark from '../../../assets/branding/dabbarha-symbol.svg';
import SymbolLight from '../../../assets/branding/dabbarha-symbol-light.svg';
import LogoDark from '../../../assets/branding/dabbarha-logo.svg';
import LogoLight from '../../../assets/branding/dabbarha-logo-light.svg';

import { sizes } from '@/constants/theme';

export type LogoVariant = 'full' | 'symbol';
export type LogoTone = 'dark' | 'light';

interface LogoProps {
  variant?: LogoVariant;
  tone?: LogoTone;
  width?: number;
  height?: number;
  style?: StyleProp<ViewStyle>;
}

function pickComponent(
  variant: LogoVariant,
  tone: LogoTone,
): React.ComponentType<{ width?: number | string; height?: number | string; fill?: string; style?: StyleProp<ViewStyle> }> {
  if (variant === 'symbol') {
    return tone === 'light' ? SymbolLight : SymbolDark;
  }
  return tone === 'light' ? LogoLight : LogoDark;
}

export function Logo({ variant = 'full', tone = 'dark', width, height, style }: LogoProps) {
  const SvgComponent = pickComponent(variant, tone);

  if (variant === 'symbol') {
    const dim = width ?? sizes.logoSymbolMd;
    return <SvgComponent width={dim} height={dim} style={style} />;
  }

  const w = width ?? sizes.logoFullWidth;
  const h = height ?? Math.round((w * 810) / 1440);
  return <SvgComponent width={w} height={h} style={style} />;
}

const styles = StyleSheet.create({});
