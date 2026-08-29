import React from 'react';
import {
  StyleSheet,
  View,
  ViewStyle,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  StyleProp,
} from 'react-native';
import { SafeAreaView, Edge } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { colors, spacing } from '@/constants/theme';

interface ScreenWrapperProps {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  contentContainerStyle?: StyleProp<ViewStyle>;
  scrollable?: boolean;
  edges?: Edge[];
  statusBarStyle?: 'auto' | 'inverted' | 'light' | 'dark';
  backgroundColor?: string;
}

export function ScreenWrapper({
  children,
  style,
  contentContainerStyle,
  scrollable = false,
  edges = ['top', 'left', 'right'],
  statusBarStyle = 'dark',
  backgroundColor = colors.background,
}: ScreenWrapperProps) {
  return (
    <SafeAreaView
      style={[styles.safeArea, { backgroundColor }, style]}
      edges={edges}
    >
      <StatusBar style={statusBarStyle} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.container}
      >
        {scrollable ? (
          <ScrollView
            style={styles.container}
            contentContainerStyle={[styles.scrollContent, contentContainerStyle]}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            {children}
          </ScrollView>
        ) : (
          <View style={[styles.container, contentContainerStyle]}>
            {children}
          </View>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
  },
  container: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    padding: spacing.md,
  },
});
