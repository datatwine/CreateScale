// createscale-app/src/ads/AdBadge.js
//
// Google requires a visible "Ad"/"Sponsored" attribution on every native ad.
// Styled as a small pill that echoes the app's existing cream chips, so it
// reads as native chrome — not a warning label.
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { COLORS } from "../config/theme";

export default function AdBadge({ label = "Sponsored", style }) {
  return (
    <View style={[styles.badge, style]}>
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    backgroundColor: COLORS.cream, // #FFF1E0 — same as profession/person chips
    borderWidth: 1,
    borderColor: COLORS.divider, // #E9E2D8
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
    alignSelf: "flex-start",
  },
  text: {
    fontSize: 10,
    fontWeight: "700",
    color: COLORS.textMuted, // #8C8077
    letterSpacing: 0.3,
  },
});
