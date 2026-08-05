// App.js

import React, { useContext } from "react";
import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { AuthProvider, AuthContext } from "./src/context/AuthContext";

// Screens
import LoginScreen from "./src/screens/LoginScreen";
import SignupScreen from "./src/screens/SignupScreen";
import ProfileScreen from "./src/screens/ProfileScreen";
import GlobalFeedScreen from "./src/screens/GlobalFeedScreen";
import ProfileDetailScreen from "./src/screens/ProfileDetailScreen";
import BookingsScreen from "./src/screens/BookingsScreen";
import LiveEventsScreen from "./src/screens/LiveEventsScreen";
import PerformerPayoutsScreen from "./src/screens/PerformerPayoutsScreen";
import ClientPaymentsScreen from "./src/screens/ClientPaymentsScreen";
import EditProfileScreen from "./src/screens/EditProfileScreen";

import { View, Text, StatusBar, StyleSheet } from "react-native";
import { COLORS } from "./src/config/theme";

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

const WebTheme = {
  ...DefaultTheme,
  dark: false,
  colors: {
    ...DefaultTheme.colors,
    background: COLORS.background,
    card: COLORS.card,
    text: COLORS.textPrimary,
    border: COLORS.divider,
    primary: COLORS.accent,
  },
};

function MainTabs() {
  const insets = useSafeAreaInsets();
  // Lift the bar off the very bottom edge so it reads as a floating pill and
  // clears the home-indicator zone. On devices without a home indicator
  // (insets.bottom === 0) fall back to a fixed gap.
  const bottomGap = insets.bottom > 0 ? insets.bottom : 12;

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: COLORS.accent,
        tabBarInactiveTintColor: COLORS.textMuted,
        tabBarItemStyle: { paddingVertical: 6 },
        tabBarStyle: {
          // True floating overlay: absolutely positioned over screen content
          // (instead of sitting in normal layout flow and pushing it up), so
          // list content is visible scrolling behind/around the pill. Screens
          // add TAB_BAR_CLEARANCE bottom padding so their last item still
          // clears it.
          position: "absolute",
          left: 16,
          right: 16,
          bottom: bottomGap,
          backgroundColor: COLORS.card,
          // Full ink border + rounded corners = the app's stamp aesthetic.
          borderWidth: 2,
          borderColor: COLORS.ink,
          borderRadius: 18,
          height: 62,
          paddingBottom: 0,
          // Soft shadow so it hovers above the content.
          shadowColor: COLORS.ink,
          shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.15,
          shadowRadius: 8,
          elevation: 8,
        },
      }}
    >
      <Tab.Screen
        name="GlobalFeed"
        component={GlobalFeedScreen}
        options={{
          tabBarLabel: "Feed",
          tabBarIcon: ({ color }) => (
            <Ionicons name="home-outline" size={20} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="LiveEvents"
        component={LiveEventsScreen}
        options={{
          tabBarLabel: "Events",
          tabBarIcon: ({ color }) => (
            <Ionicons name="calendar-outline" size={20} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Bookings"
        component={BookingsScreen}
        options={{
          tabBarLabel: "Bookings",
          tabBarIcon: ({ color }) => (
            <Ionicons name="briefcase-outline" size={20} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          tabBarLabel: "Profile",
          tabBarIcon: ({ color }) => (
            <Ionicons name="person-outline" size={20} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}

function RootNavigator() {
  const { token, initializing } = useContext(AuthContext);

  if (initializing) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>Loading your session…</Text>
      </View>
    );
  }

  return (
    <NavigationContainer theme={WebTheme}>
      {token ? (
        <Stack.Navigator screenOptions={{ headerShown: false, animation: "fade" }}>
          <Stack.Screen name="MainTabs" component={MainTabs} />
          <Stack.Screen name="ProfileDetail" component={ProfileDetailScreen} />
          {/* Bookings — engagement dashboard for client + performer */}
          <Stack.Screen name="Bookings" component={BookingsScreen} />
          {/* LiveEvents — public accepted engagements, upcoming + past */}
          <Stack.Screen name="LiveEvents" component={LiveEventsScreen} />
          {/* Payment screens — linked from settings drawer */}
          <Stack.Screen name="PerformerPayouts" component={PerformerPayoutsScreen} />
          <Stack.Screen name="ClientPayments" component={ClientPaymentsScreen} />
          <Stack.Screen name="EditProfile" component={EditProfileScreen} />
        </Stack.Navigator>
      ) : (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Signup" component={SignupScreen} />
        </Stack.Navigator>
      )}
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <View style={{ flex: 1, backgroundColor: COLORS.background }}>
          <StatusBar barStyle="light-content" backgroundColor={COLORS.black} translucent={false} />
          <RootNavigator />
        </View>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: COLORS.background,
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    color: COLORS.loadingText,
    fontSize: 18,
  },
});
