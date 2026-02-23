import React, { useState, useContext } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from "react-native";
import { AuthContext } from "../context/AuthContext";
import SocialLoginButtons from "../components/SocialLoginButtons";

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
    <KeyboardAvoidingView
      style={styles.fullScreen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {/* Background split: left black, center orange line, right pale white */}
      <View style={styles.backgroundRow}>
        <View style={styles.leftHalf} />
        <View style={styles.divider} />
        <View style={styles.rightHalf} />
      </View>

      {/* Foreground content overlays the background */}
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
            placeholderTextColor="#888"
            autoCapitalize="none"
            value={username}
            onChangeText={setUsername}
          />

          <TextInput
            style={styles.input}
            placeholder="Password"
            placeholderTextColor="#888"
            secureTextEntry
            value={password}
            onChangeText={setPassword}
          />

          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <TouchableOpacity
            style={[styles.primaryButton, loading && styles.disabledButton]}
            onPress={handleLoginPress}
            disabled={loading}
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
  );
}

const ORANGE = "#d17700";
const PALE_WHITE = "#fef5e7";

const styles = StyleSheet.create({
  fullScreen: {
    flex: 1,
    backgroundColor: "#000000",
  },
  backgroundRow: {
    // This view fills the screen and draws the 3 background stripes.
    ...StyleSheet.absoluteFillObject,
    flexDirection: "row",
  },
  leftHalf: {
    flex: 1,
    backgroundColor: "#000000",
  },
  divider: {
    width: 4,
    backgroundColor: ORANGE,
  },
  rightHalf: {
    flex: 1,
    backgroundColor: PALE_WHITE,
  },
  overlay: {
    // Foreground content is stacked over background using absolute fill.
    flex: 1,
    paddingHorizontal: 24,
    justifyContent: "center",
  },
  brandTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: ORANGE,
    textAlign: "center",
    marginBottom: 4,
  },
  brandSubtitle: {
    fontSize: 14,
    color: "#f9f9f9",
    textAlign: "center",
    marginBottom: 24,
  },
  card: {
    backgroundColor: "rgba(0, 0, 0, 0.7)",
    borderRadius: 16,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.3,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: "600",
    color: PALE_WHITE,
    marginBottom: 4,
  },
  cardSubtitle: {
    fontSize: 13,
    color: "#cccccc",
    marginBottom: 16,
  },
  input: {
    backgroundColor: "#111111",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "#ffffff",
    marginBottom: 12,
    borderWidth: 1,
    borderColor: "#333333",
  },
  errorText: {
    color: "#ff6666",
    marginBottom: 8,
    fontSize: 13,
  },
  primaryButton: {
    backgroundColor: ORANGE,
    borderRadius: 999,
    paddingVertical: 12,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 4,
  },
  primaryButtonText: {
    color: "#ffffff",
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
    color: "#f1f1f1",
    fontSize: 14,
  },
  secondaryButtonHighlight: {
    color: ORANGE,
    fontWeight: "600",
  },
});
