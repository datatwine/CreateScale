// App.js

import React, { useContext } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { AuthProvider, AuthContext } from "./src/context/AuthContext";

// Screens
import LoginScreen from "./src/screens/LoginScreen";
import SignupScreen from "./src/screens/SignupScreen";
import ProfileScreen from "./src/screens/ProfileScreen";
import GlobalFeedScreen from "./src/screens/GlobalFeedScreen";
import ProfileDetailScreen from "./src/screens/ProfileDetailScreen";


// Later: we'll add a "MainApp" or "Home" stack that includes GlobalFeed, etc.
// For now, we'll just make a placeholder.
import { View, Text, StyleSheet } from "react-native";

const Stack = createNativeStackNavigator();

// Very simple placeholder for "logged-in area"
function PlaceholderHomeScreen() {
  const { user } = useContext(AuthContext);

  return (
    <View style={styles.homeContainer}>
      <Text style={styles.homeTitle}>You are logged in 🎉</Text>
      <Text style={styles.homeSubtitle}>
        {user ? `Hello, ${user.username}` : "We haven't loaded your profile yet."}
      </Text>
      <Text style={styles.homeSubtitle}>
        Later this will be your Global Feed / Dashboard screen.
      </Text>
    </View>
  );
}

// A component that chooses which stack to show based on auth state
function RootNavigator() {
  const { token, initializing } = useContext(AuthContext);

  if (initializing) {
    // Tiny splash-like screen while we read AsyncStorage.
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>Loading your session…</Text>
      </View>
    );
  }

  return (
    <NavigationContainer>
      {token ? (
        // User is logged in -> show “app” stack
        <Stack.Navigator>
          {/* After login, go straight to the profile view */}
          <Stack.Screen name="Profile" component={ProfileScreen} />
          {/* GlobalFeed — navigated to from the "Global feed" pill in ProfileScreen */}
          <Stack.Screen name="GlobalFeed" component={GlobalFeedScreen} />
          {/* ProfileDetail — read-only view of another user, with hire flow */}
          <Stack.Screen name="ProfileDetail" component={ProfileDetailScreen} />
        </Stack.Navigator>
      ) : (
        // User is not logged in -> show auth stack
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Signup" component={SignupScreen} />
        </Stack.Navigator>
      )}
    </NavigationContainer>
  );
}

export default function App() {
  // Wrap the entire app inside AuthProvider so all screens can use AuthContext.
  return (
    <AuthProvider>
      <RootNavigator />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: "#000000",
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    color: "#fef5e7", // pale white-ish
    fontSize: 18,
  },
  homeContainer: {
    flex: 1,
    backgroundColor: "#f9f9f9",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  homeTitle: {
    fontSize: 24,
    fontWeight: "700",
    color: "#d17700", // your orange
    marginBottom: 8,
  },
  homeSubtitle: {
    fontSize: 16,
    color: "#444",
    textAlign: "center",
    marginTop: 4,
  },
});
