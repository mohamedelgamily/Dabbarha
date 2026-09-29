import { t, isArabic } from '@/i18n';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Tabs } from 'expo-router';
import { typography } from '@/constants/theme';
import {
  LayoutDashboard,
  TrendingUp,
  CreditCard,
  User,
} from 'lucide-react-native';




export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#D8EBB6',
        tabBarInactiveTintColor: '#94AEA7',
        tabBarStyle: [styles.tabBar, { height: 62 + Math.max(insets.bottom, 10), paddingBottom: Math.max(insets.bottom, 10) }],
        tabBarLabelStyle: [styles.tabBarLabel, isArabic() && { fontFamily: 'NotoNaskhArabic', fontSize: 12, lineHeight: 20, letterSpacing: 0 }],
        tabBarItemStyle: styles.tabBarItem,
        tabBarHideOnKeyboard: true,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("Home"),
          tabBarLabel: t("Home"),
          tabBarIcon: ({ color, focused }) => (
            <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
              <LayoutDashboard
                size={20}
                color={color}
                strokeWidth={focused ? 2.25 : 1.75}
              />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="obligations"
        options={{
          title: t("Obligations"),
          tabBarLabel: t("Obligations"),
          tabBarIcon: ({ color, focused }) => (
            <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
              <CreditCard
                size={20}
                color={color}
                strokeWidth={focused ? 2.25 : 1.75}
              />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t("Profile"),
          tabBarLabel: t("Profile"),
          tabBarIcon: ({ color, focused }) => (
            <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
              <User
                size={20}
                color={color}
                strokeWidth={focused ? 2.25 : 1.75}
              />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="forecast"
        options={{
          title: t("Forecast"),
          tabBarLabel: t("Forecast"),
          tabBarIcon: ({ color, focused }) => (
            <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
              <TrendingUp
                size={20}
                color={color}
                strokeWidth={focused ? 2.25 : 1.75}
              />
            </View>
          ),
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: '#022E31',
    borderTopLeftRadius: 25,
    borderTopRightRadius: 25,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(2, 38, 45, 0.08)',
    paddingTop: 8,
    shadowColor: '#010D10',
    shadowOffset: { width: 0, height: -3 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 6,
  },
  tabBarItem: {
    paddingVertical: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconWrap: {
    width: 34,
    height: 30,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconWrapActive: {
    backgroundColor: 'rgba(186, 215, 168, 0.12)',
  },
  tabBarLabel: {
    fontFamily: typography.fontFamily,
    fontSize: 10.5,
    fontWeight: '600',
    letterSpacing: 0.2,
    marginTop: 2,
    lineHeight: 13,
  },
});