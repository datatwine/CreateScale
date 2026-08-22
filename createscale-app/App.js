// App.js

import React, { useContext, useEffect, useRef } from "react";
import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { AuthProvider, AuthContext } from "./src/context/AuthContext";
import {
  registerForPushNotifications,
  setupNotificationResponseHandling,
} from "./src/notifications";

// Screens
import LoginScreen from "./src/screens/LoginScreen";
import SignupScreen from "./src/screens/SignupScreen";
import ForgotPasswordScreen from "./src/screens/ForgotPasswordScreen";
import ProfileScreen from "./src/screens/ProfileScreen";
import GlobalFeedScreen from "./src/screens/GlobalFeedScreen";
import ProfileDetailScreen from "./src/screens/ProfileDetailScreen";
import BookingsScreen from "./src/screens/BookingsScreen";
import LiveEventsScreen from "./src/screens/LiveEventsScreen";
import PerformerPayoutsScreen from "./src/screens/PerformerPayoutsScreen";
import ClientPaymentsScreen from "./src/screens/ClientPaymentsScreen";
import EditProfileScreen from "./src/screens/EditProfileScreen";
import LeaveReviewScreen from "./src/screens/LeaveReviewScreen";

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
  const navigationRef = useRef(null);

  // Register for push notifications whenever the user logs in. Needs the
  // auth token (to tell Django which device belongs to whom), so this can
  // only run once token is set — not during the initial loading state.
  useEffect(() => {
    if (token) {
      registerForPushNotifications(token);
    }
  }, [token]);

  // Tap-handling is set up once, decoupled from login — tying it to the
  // token effect above would attach another live listener on every
  // re-login, so a single tap would fire navigate() once per stacked
  // listener. The cleanup removes the listener on unmount.
  //
  // Gated on !initializing rather than mount ([]): NavigationContainer
  // (and navigationRef.current) doesn't exist until the loading screen
  // below is past — it's blocked on fetchAuthMe(), a network call. Firing
  // on mount would run the cold-start check while the ref is still null,
  // silently dropping a launch tap for exactly the users who can receive
  // one (logged-in, stored token). initializing flips true → false once,
  // never back, so this still only sets up the listener a single time —
  // just at the point the ref is actually populated instead of before it.
  useEffect(() => {
    if (initializing) {
      return;
    }
    return setupNotificationResponseHandling(navigationRef);
  }, [initializing]);

  if (initializing) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>Loading your session…</Text>
      </View>
    );
  }

  return (
    <NavigationContainer ref={navigationRef} theme={WebTheme}>
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
          <Stack.Screen name="LeaveReview" component={LeaveReviewScreen} />
        </Stack.Navigator>
      ) : (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Signup" component={SignupScreen} />
          <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
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
