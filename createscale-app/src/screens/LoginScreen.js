import React, { useState, useContext } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ScrollView, StatusBar } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { AuthContext } from "../context/AuthContext";
import SocialLoginButtons from "../components/SocialLoginButtons";
import { COLORS } from "../config/theme";

export default function LoginScreen({ navigation }) {
  const { login } = useContext(AuthContext);

  // Controlled inputs to hold username & password typed by the user
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  // UI state: loading + error message
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLoginPress = async () => {
    // Basic guard to avoid empty credentials
    if (!username || !password) {
      setError("Please enter both username and password.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      // Call the AuthContext login, which talks to Django and stores token.
      await login(username, password);
      // If login is successful, RootNavigator will switch to "Home".
    } catch (err) {
      setError(err.message || "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  const goToSignup = () => {
    navigation.navigate("Signup");
  };

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor="#000000" translucent={false} />
      <KeyboardAvoidingView
        style={styles.fullScreen}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView contentContainerStyle={styles.overlay}>
          <Text style={styles.brandTitle}>CreateScale</Text>
          <Text style={styles.brandSubtitle}>Log in to your live experiences</Text>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Welcome back 👋</Text>
            <Text style={styles.cardSubtitle}>
              Use the same username & password you use on the website.
            </Text>

            <TextInput
              style={styles.input}
              placeholder="Username"
              placeholderTextColor={COLORS.textMuted}
              autoCapitalize="none"
              value={username}
              onChangeText={setUsername}
            />

            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor={COLORS.textMuted}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />

            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <TouchableOpacity
              activeOpacity={0.85}
              onPress={handleLoginPress}
              disabled={loading}
              style={[styles.primaryButton, loading && styles.disabledButton]}
            >
              <Text style={styles.primaryButtonText}>
                {loading ? "Logging in..." : "Log in"}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={goToSignup} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>
                New here? <Text style={styles.secondaryButtonHighlight}>Sign up</Text>
              </Text>
            </TouchableOpacity>

            <SocialLoginButtons />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#000",
  },
  fullScreen: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  overlay: {
    flexGrow: 1,
    paddingHorizontal: 24,
    justifyContent: "flex-start",
    paddingTop: 60,
  },
  brandTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: COLORS.accent,
    textAlign: "center",
    marginBottom: 4,
  },
  brandSubtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: "center",
    marginBottom: 24,
  },
  card: {
    backgroundColor: COLORS.card,
    borderRadius: 16,
    padding: 20,
    borderWidth: 2,
    borderColor: COLORS.ink,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: "600",
    color: COLORS.textPrimary,
    marginBottom: 4,
  },
  cardSubtitle: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginBottom: 16,
  },
  input: {
    backgroundColor: COLORS.cream,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: COLORS.textPrimary,
    marginBottom: 12,
    borderWidth: 2,
    borderColor: COLORS.ink,
    fontSize: 14,
  },
  errorText: {
    color: "#B71C1C",
    marginBottom: 8,
    fontSize: 13,
  },
  primaryButton: {
    borderRadius: 999,
    paddingVertical: 12,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 4,
    backgroundColor: COLORS.accent,
    borderWidth: 2,
    borderColor: COLORS.ink,
    // 3D stamp shadow (bottom-right)
    shadowColor: COLORS.ink,
    shadowOpacity: 1,
    shadowRadius: 0,
    shadowOffset: { width: 3, height: 3 },
    elevation: 6,
  },
  primaryButtonText: {
    color: COLORS.card,
    fontWeight: "700",
    fontSize: 16,
  },
  disabledButton: {
    opacity: 0.6,
  },
  secondaryButton: {
    marginTop: 12,
    alignItems: "center",
  },
  secondaryButtonText: {
    color: COLORS.textSecondary,
    fontSize: 14,
  },
  secondaryButtonHighlight: {
    color: COLORS.accent,
    fontWeight: "600",
  },
});
