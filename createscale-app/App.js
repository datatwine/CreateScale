// App.js

import React, { useContext } from "react";
import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
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
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: COLORS.accent,
        tabBarInactiveTintColor: COLORS.textMuted,
        tabBarStyle: {
          backgroundColor: COLORS.card,
          borderTopColor: COLORS.ink,
          borderTopWidth: 2,
          height:55,
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
    <AuthProvider>
      <View style={{ flex: 1, backgroundColor: COLORS.background }}>
        <StatusBar barStyle="light-content" backgroundColor="#000000" translucent={false} />
        <RootNavigator />
      </View>
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: "#FFF8EE",
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    color: "#fef5e7",
    fontSize: 18,
  },
});
