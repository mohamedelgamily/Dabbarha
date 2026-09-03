declare module '*.svg' {
  import { ComponentType } from 'react';
  import { StyleProp, ViewStyle } from 'react-native';
  const svg: ComponentType<{
    width?: number | string;
    height?: number | string;
    fill?: string;
    style?: StyleProp<ViewStyle>;
  }> | { default: ComponentType<{ width?: number | string; height?: number | string; fill?: string; style?: StyleProp<ViewStyle> }> };
  export default svg;
}
