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

import React, { useContext, useRef, useState } from "react";
import {
  Animated,          // React Native's animation primitive
  Dimensions,        // Used to get screen height, so we can force scrolling
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

import { AuthContext } from "../context/AuthContext";
import { signupWithCredentials } from "../api/auth";

// ----- Theme constants (so you can reuse them later) -----
const { height: WINDOW_HEIGHT } = Dimensions.get("window");

const PRIMARY_ORANGE = "#e68513";   // soft orange accent
const SOFT_WHITE = "#fff4dd";       // pale, slightly yellow white
const DEEP_BLACK = "#000000";       // pure black background

// First sentence broken into words so we can animate each separately
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
  // Auth context — we call login() after signup so the user is auto-logged-in
  const { login } = useContext(AuthContext);

  // This Animated value tracks vertical scroll position.
  // We mostly use it to detect "user has started scrolling" rather than
  // for fancy parallax.
  const scrollY = useRef(new Animated.Value(0)).current;

  // We need to make sure we only start the animation ONCE.
  const hasStartedAnimations = useRef(false);

  // For each word we want:
  //   - opacity: 0 -> 1
  //   - translateY: 16 -> 0 (moves upwards a bit, like a fountain)
  const wordAnimations = useRef(
    introWords.map(() => ({
      opacity: new Animated.Value(0),
      translateY: new Animated.Value(16),
    }))
  ).current;

  // Second line ("Come, be a part of them!") animation controller.
  // 0 = hidden, 1 = fully visible + bounced.
  const secondLineAnim = useRef(new Animated.Value(0)).current;

  // ---- Form state ----
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");   // <-- shows backend validation errors

  // Called the first time the user scrolls a little bit.
  // Runs a staggered animation for each word, then the trampoline for line 2.
  const startIntroAnimation = () => {
    if (hasStartedAnimations.current) return; // guard
    hasStartedAnimations.current = true;

    // Per-word animations: each word fades in and slides up slightly.
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

    // Sequence:
    // 1. Stagger the words (small delay between each)
    // 2. When done, run the trampoline on the second line
    Animated.sequence([
      Animated.stagger(90, perWordAnimations),
      Animated.spring(secondLineAnim, {
        toValue: 1,
        friction: 5,   // lower friction = more bounce
        tension: 80,
        useNativeDriver: true,
      }),
    ]).start();
  };

  // Scroll callback. We only care that the user has moved a little.
  const handleScroll = (event) => {
    const offsetY = event.nativeEvent.contentOffset.y || 0;
    if (offsetY > 10) {
      startIntroAnimation();
    }
  };

  // ---- Real signup handler ----
  // Calls the Django API, then auto-logs the user in via AuthContext.
  const handleSubmit = async () => {
    // Basic client-side guard before hitting the network
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
      // 1. Create account on the backend (returns {token, user_id, username})
      const data = await signupWithCredentials({ username, email, password1, password2 });

      // 2. Auto-login: use the returned token via AuthContext.login()
      //    login() expects (username, password) and calls the token API internally,
      //    so we just call it with the credentials we already have.
      await login(username, password1);

      // Navigation is automatic — AuthContext sets the token, and
      // RootNavigator switches to the authenticated stack (ProfileScreen).
    } catch (err) {
      setError(err.message || "Signup failed. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // KeyboardAvoidingView behaviour for iOS vs Android
  const keyboardBehavior = Platform.OS === "ios" ? "padding" : undefined;

  return (
    <View style={styles.screenRoot}>
      <StatusBar barStyle="light-content" />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={keyboardBehavior}>
        {/* Animated.ScrollView so we can react to scroll */}
        <Animated.ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          scrollEventThrottle={16}        // ~60fps scroll events
          onScroll={handleScroll}         // fires our animation trigger
        >
          {/* ---------- HERO SECTION (text + split background) ---------- */}
          <View style={styles.heroContainer}>
            {/* Background split: left black, right pale white, orange stripe in middle */}
            <View style={styles.backgroundRow}>
              <View style={styles.leftHalf} />
              <View style={styles.rightHalf} />
              <View style={styles.verticalStripe} />
            </View>

            {/* Foreground hero text */}
            <View style={styles.heroTextWrapper}>
              {/* Line 1: word-by-word fountain animation */}
              <View style={styles.heroLine1Row}>
                {introWords.map((word, index) => (
                  <Animated.Text
                    key={`${word}-${index}`}
                    style={[
                      styles.heroLine1Word,
                      {
                        opacity: wordAnimations[index].opacity,
                        transform: [
                          { translateY: wordAnimations[index].translateY },
                        ],
                      },
                    ]}
                  >
                    {word}
                    {index !== introWords.length - 1 ? " " : ""}
                  </Animated.Text>
                ))}
              </View>

              {/* Line 2: trampoline / bounce effect */}
              <Animated.Text
                style={[
                  styles.heroLine2,
                  {
                    opacity: secondLineAnim,
                    transform: [
                      {
                        // slides up as it appears
                        translateY: secondLineAnim.interpolate({
                          inputRange: [0, 1],
                          outputRange: [40, 0],
                        }),
                      },
                      {
                        // trampoline scale
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

          {/* ---------- FORM SECTION (below the fold) ---------- */}
          <View style={styles.formSection}>
            <View style={styles.formCardShadow}>
              <View style={styles.formCard}>
                <Text style={styles.formTitle}>Create your account ✨</Text>
                <Text style={styles.formSubtitle}>
                  Join as an explorer, performer, or potential client — we’ll
                  wire in all the roles later. For now, it’s just your basic
                  account.
                </Text>

                {/* Username */}
                <TextInput
                  placeholder="Username"
                  placeholderTextColor="#d7d2c8"
                  style={styles.input}
                  value={username}
                  onChangeText={setUsername}
                  autoCapitalize="none"
                  autoCorrect={false}
                  textContentType="username"
                />

                {/* Email */}
                <TextInput
                  placeholder="Email"
                  placeholderTextColor="#d7d2c8"
                  style={styles.input}
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  textContentType="emailAddress"
                />

                {/* Password */}
                <TextInput
                  placeholder="Password"
                  placeholderTextColor="#d7d2c8"
                  style={styles.input}
                  value={password1}
                  onChangeText={setPassword1}
                  secureTextEntry
                  textContentType="password"
                />

                {/* Confirm password */}
                <TextInput
                  placeholder="Confirm password"
                  placeholderTextColor="#d7d2c8"
                  style={styles.input}
                  value={password2}
                  onChangeText={setPassword2}
                  secureTextEntry
                />

                {/* Validation error message (from backend or client-side) */}
                {error ? (
                  <Text style={styles.errorText}>{error}</Text>
                ) : null}

                {/* Chunky dopamine button */}
                <TouchableOpacity
                  style={styles.signupButton}
                  activeOpacity={0.8}
                  onPress={handleSubmit}
                  disabled={isSubmitting}
                >
                  <Text style={styles.signupButtonText}>
                    {isSubmitting ? "Signing you up..." : "Sign up"}
                  </Text>
                </TouchableOpacity>

                {/* Link to login */}
                <View style={styles.loginRow}>
                  <Text style={styles.loginLabel}>
                    Already have an account?
                  </Text>
                  <TouchableOpacity
                    onPress={() => navigation.navigate("Login")}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Text style={styles.loginLink}>Log in</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          </View>
        </Animated.ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

// ---------------------- STYLES ----------------------
const styles = StyleSheet.create({
  screenRoot: {
    flex: 1,
    backgroundColor: DEEP_BLACK,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 40,
  },

  // Hero takes >100% of the viewport so the form starts *below* first screen
  heroContainer: {
    minHeight: WINDOW_HEIGHT * 1.15, // tweak this (1.1 – 1.3) if needed
    justifyContent: "center",
  },

  // Background split (black / soft white + orange divider)
  backgroundRow: {
    ...StyleSheet.absoluteFillObject,
    flexDirection: "row",
  },
  leftHalf: {
    flex: 1,
    backgroundColor: DEEP_BLACK,
  },
  rightHalf: {
    flex: 1,
    backgroundColor: SOFT_WHITE,
  },
  verticalStripe: {
    position: "absolute",
    width: 3,
    left: "50%",
    top: 0,
    bottom: 0,
    backgroundColor: PRIMARY_ORANGE,
  },

  // Hero text layout
  heroTextWrapper: {
    paddingHorizontal: 28,
    paddingTop: 72,
  },
  heroLine1Row: {
    flexDirection: "row",
    flexWrap: "wrap",
    maxWidth: "88%",
  },
  heroLine1Word: {
    fontSize: 32,
    fontWeight: "800",
    color: PRIMARY_ORANGE,
    letterSpacing: 0.2,
  },
  heroLine2: {
    marginTop: 18,
    fontSize: 26,
    fontWeight: "700",
    color: "#ffffff",
    maxWidth: "80%",
  },

  // Form section sits on soft white background and card pops above it
  formSection: {
    paddingHorizontal: 18,
    paddingTop: 24,
    paddingBottom: 8,
    backgroundColor: SOFT_WHITE,
  },
  formCardShadow: {
    borderRadius: 28,
    shadowColor: "#000",
    shadowOpacity: 0.32,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 12 },
    elevation: 12, // Android shadow
  },
  formCard: {
    borderRadius: 28,
    backgroundColor: "#111111",
    paddingHorizontal: 22,
    paddingVertical: 26,
  },
  formTitle: {
    fontSize: 26,
    fontWeight: "800",
    color: "#ffffff",
    marginBottom: 6,
  },
  formSubtitle: {
    fontSize: 15,
    lineHeight: 20,
    color: "#d7d2c8",
    marginBottom: 18,
  },
  input: {
    height: 48,
    borderRadius: 14,
    paddingHorizontal: 14,
    backgroundColor: "#222222",
    borderWidth: 1,
    borderColor: "#333333",
    color: "#ffffff",
    marginBottom: 12,
  },
  errorText: {
    color: "#ff6666",
    fontSize: 13,
    marginBottom: 8,
    lineHeight: 18,
  },
  signupButton: {
    marginTop: 4,
    height: 50,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: PRIMARY_ORANGE,
  },
  signupButtonText: {
    fontSize: 18,
    fontWeight: "700",
    color: "#ffffff",
  },
  loginRow: {
    flexDirection: "row",
    justifyContent: "center",
    marginTop: 18,
  },
  loginLabel: {
    color: "#e1ddd3",
    fontSize: 14,
  },
  loginLink: {
    marginLeft: 6,
    fontSize: 14,
    fontWeight: "700",
    color: PRIMARY_ORANGE,
  },
});
