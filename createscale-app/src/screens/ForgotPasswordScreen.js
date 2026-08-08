import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StatusBar,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { forgotPassword } from "../api/auth";
import { COLORS } from "../config/theme";

export default function ForgotPasswordScreen({ navigation }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  const handleSendPress = async () => {
    if (!email) {
      setError("Please enter your email address.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err.message || "Failed to send reset link.");
    } finally {
      setLoading(false);
    }
  };

  const goToLogin = () => {
    navigation.navigate("Login");
  };

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.black} translucent={false} />
      <KeyboardAvoidingView
        style={styles.fullScreen}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView contentContainerStyle={styles.overlay}>
          <Text style={styles.brandTitle}>CreateScale</Text>
          <Text style={styles.brandSubtitle}>Reset your password</Text>

          <View style={styles.card}>
            {sent ? (
              <>
                <Text style={styles.cardTitle}>Check your email 📬</Text>
                <Text style={styles.cardSubtitle}>
                  If an account exists for that email, a password reset link is on
                  its way. Open it in your browser to choose a new password, then
                  log in here.
                </Text>
                <TouchableOpacity
                  activeOpacity={0.85}
                  onPress={goToLogin}
                  style={styles.primaryButton}
                >
                  <Text style={styles.primaryButtonText}>Back to Login</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                <Text style={styles.cardTitle}>Forgot your password?</Text>
                <Text style={styles.cardSubtitle}>
                  Enter the email you signed up with and we’ll send you a link to
                  reset your password.
                </Text>

                <TextInput
                  style={styles.input}
                  placeholder="Email"
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  textContentType="emailAddress"
                  value={email}
                  onChangeText={setEmail}
                />

                {error ? <Text style={styles.errorText}>{error}</Text> : null}

                <TouchableOpacity
                  activeOpacity={0.85}
                  onPress={handleSendPress}
                  disabled={loading}
                  style={[styles.primaryButton, loading && styles.disabledButton]}
                >
                  <Text style={styles.primaryButtonText}>
                    {loading ? "Sending..." : "Send Reset Link"}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity onPress={goToLogin} style={styles.secondaryButton}>
                  <Text style={styles.secondaryButtonText}>
                    Remembered it?{" "}
                    <Text style={styles.secondaryButtonHighlight}>Back to Login</Text>
                  </Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.black,
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
    color: COLORS.error,
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
