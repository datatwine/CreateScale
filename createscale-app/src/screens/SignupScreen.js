// SignupScreen.js
// ---------------------------
// Signup screen with scroll-triggered hero animation:
//  - First line appears word-by-word ("fountain" upwards)
//  - Second line bounces in (trampoline)
//  - Form card only appears after the hero section (user must scroll)
//
// This file assumes you are using React Navigation and that
// `navigation.navigate("Login")` goes to your login screen.
// ---------------------------

import React, { useContext, useRef, useState, useEffect } from "react";
import {
  Animated,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { AuthContext } from "../context/AuthContext";
import { signupWithCredentials } from "../api/auth";
import SocialLoginButtons from "../components/SocialLoginButtons";
import { COLORS } from "../config/theme";

const introWords = [
  "Are",
  "you",
  "someone",
  "who",
  "loves",
  "live",
  "experiences?",
];

export default function SignupScreen({ navigation }) {
  const { login } = useContext(AuthContext);

  // ScrollView ref for auto-scrolling to form on mount
  const scrollViewRef = useRef(null);

  // This Animated value tracks vertical scroll position.
  // We mostly use it to detect "user has started scrolling" rather than
  // for fancy parallax.
  // const scrollY = useRef(new Animated.Value(0)).current;

  // We need to make sure we only start the animation ONCE.
  const hasStartedAnimations = useRef(false);

  const wordAnimations = useRef(
    introWords.map(() => ({
      opacity: new Animated.Value(0),
      translateY: new Animated.Value(16),
    }))
  ).current;

  const secondLineAnim = useRef(new Animated.Value(0)).current;

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => startIntroAnimation(), 300);
    return () => clearTimeout(timer);
  }, []);

  // Auto-scroll to form section on component mount
  // useEffect(() => {
  //   // Wait a moment for layout, then scroll to form (approximately 400px down)
  //   const timer = setTimeout(() => {
  //     scrollViewRef.current?.scrollTo({ y: 400, animated: true });
  //   }, 300);
  //   return () => clearTimeout(timer);
  // }, []);

  // Called the first time the user scrolls a little bit.
  // Runs a staggered animation for each word, then the trampoline for line 2.
  const startIntroAnimation = () => {
    if (hasStartedAnimations.current) return;
    hasStartedAnimations.current = true;

    const perWordAnimations = introWords.map((_, index) =>
      Animated.parallel([
        Animated.timing(wordAnimations[index].opacity, {
          toValue: 1,
          duration: 240,
          useNativeDriver: true,
        }),
        Animated.timing(wordAnimations[index].translateY, {
          toValue: 0,
          duration: 240,
          useNativeDriver: true,
        }),
      ])
    );

    Animated.sequence([
      Animated.stagger(90, perWordAnimations),
      Animated.spring(secondLineAnim, {
        toValue: 1,
        friction: 5,
        tension: 80,
        useNativeDriver: true,
      }),
    ]).start();
  };

  const handleSubmit = async () => {
    if (!username || !email || !password1 || !password2) {
      setError("Please fill in all fields.");
      return;
    }
    if (password1 !== password2) {
      setError("Passwords do not match.");
      return;
    }

    if (isSubmitting) return;
    setIsSubmitting(true);
    setError("");

    try {
      await signupWithCredentials({ username, email, password1, password2 });
      await login(username, password1);
    } catch (err) {
      setError(err.message || "Signup failed. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={["top"]}>
      <StatusBar barStyle="light-content" backgroundColor="#000000" translucent={false} />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <Animated.ScrollView
          ref={scrollViewRef}
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
        >
          {/* Hero */}
          <View style={styles.heroSection}>
            <View style={styles.heroTextWrapper}>
              <View style={styles.heroLine1Row}>
                {introWords.map((word, index) => (
                  <Animated.Text
                    key={`${word}-${index}`}
                    style={[
                      styles.heroLine1Word,
                      {
                        opacity: wordAnimations[index].opacity,
                        transform: [{ translateY: wordAnimations[index].translateY }],
                      },
                    ]}
                  >
                    {word}
                    {index !== introWords.length - 1 ? " " : ""}
                  </Animated.Text>
                ))}
              </View>

              <Animated.Text
                style={[
                  styles.heroLine2,
                  {
                    opacity: secondLineAnim,
                    transform: [
                      {
                        translateY: secondLineAnim.interpolate({
                          inputRange: [0, 1],
                          outputRange: [40, 0],
                        }),
                      },
                      {
                        scale: secondLineAnim.interpolate({
                          inputRange: [0, 0.6, 1],
                          outputRange: [0.7, 1.08, 1],
                        }),
                      },
                    ],
                  },
                ]}
              >
                Come, be a part of them!
              </Animated.Text>
            </View>
          </View>

          {/* Form */}
          <View style={styles.formSection}>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Create your account ✨</Text>
              <Text style={styles.cardSubtitle}>
                Join as an explorer, performer, or potential client.
              </Text>

              <TextInput
                placeholder="Username"
                placeholderTextColor={COLORS.textMuted}
                style={styles.input}
                value={username}
                onChangeText={setUsername}
                autoCapitalize="none"
                autoCorrect={false}
              />

              <TextInput
                placeholder="Email"
                placeholderTextColor={COLORS.textMuted}
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                keyboardType="email-address"
              />

              <TextInput
                placeholder="Password"
                placeholderTextColor={COLORS.textMuted}
                style={styles.input}
                value={password1}
                onChangeText={setPassword1}
                secureTextEntry
              />

              <TextInput
                placeholder="Confirm password"
                placeholderTextColor={COLORS.textMuted}
                style={styles.input}
                value={password2}
                onChangeText={setPassword2}
                secureTextEntry
              />

              {error ? <Text style={styles.errorText}>{error}</Text> : null}

              <TouchableOpacity
                activeOpacity={0.85}
                onPress={handleSubmit}
                disabled={isSubmitting}
                style={[styles.primaryButton, isSubmitting && styles.disabledButton]}
              >
                <Text style={styles.primaryButtonText}>
                  {isSubmitting ? "Signing you up..." : "Sign up"}
                </Text>
              </TouchableOpacity>

              <View style={styles.loginRow}>
                <Text style={styles.loginLabel}>Already have an account?</Text>
                <TouchableOpacity onPress={() => navigation.navigate("Login")}>
                  <Text style={styles.loginLink}>Log in</Text>
                </TouchableOpacity>
              </View>

              <SocialLoginButtons />
            </View>
          </View>
        </Animated.ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#000",
  },
  scroll: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    paddingBottom: 40,
  },
  heroSection: {
    paddingTop: 20,
    paddingBottom: 20,
  },
  heroTextWrapper: {
    paddingHorizontal: 28,
  },
  heroLine1Row: {
    flexDirection: "row",
    flexWrap: "wrap",
    maxWidth: "88%",
  },
  heroLine1Word: {
    fontSize: 32,
    fontWeight: "800",
    color: COLORS.accent,
    letterSpacing: 0.2,
    lineHeight: 36,
  },
  heroLine2: {
    marginTop: 18,
    fontSize: 26,
    fontWeight: "700",
    color: COLORS.ink,
    maxWidth: "80%",
  },
  formSection: {
    paddingHorizontal: 18,
    paddingTop: 24,
    paddingBottom: 8,
    backgroundColor: COLORS.background,
  },
  card: {
    borderRadius: 16,
    backgroundColor: COLORS.card,
    padding: 20,
    borderWidth: 2,
    borderColor: COLORS.ink,
  },
  cardTitle: {
    fontSize: 22,
    fontWeight: "700",
    color: COLORS.textPrimary,
    marginBottom: 6,
  },
  cardSubtitle: {
    fontSize: 14,
    lineHeight: 20,
    color: COLORS.textSecondary,
    marginBottom: 18,
  },
  input: {
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: COLORS.cream,
    borderWidth: 2,
    borderColor: COLORS.ink,
    color: COLORS.textPrimary,
    marginBottom: 12,
    fontSize: 14,
  },
  errorText: {
    color: "#B71C1C",
    fontSize: 13,
    marginBottom: 8,
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
  loginRow: {
    flexDirection: "row",
    justifyContent: "center",
    marginTop: 18,
  },
  loginLabel: {
    color: COLORS.textSecondary,
    fontSize: 14,
  },
  loginLink: {
    marginLeft: 6,
    fontSize: 14,
    fontWeight: "700",
    color: COLORS.accent,
  },
});
