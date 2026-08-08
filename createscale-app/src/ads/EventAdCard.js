// createscale-app/src/ads/EventAdCard.js
//
// Mirrors LiveEventsScreen's EventCard structure (top row → title → detail
// row → chip), full-width, matching border radius and card padding.
import React from "react";
import { View, Text, Image, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";
import AdBadge from "./AdBadge";

export default function EventAdCard({ ad, onPress }) {
  const iconSource = ad.icon?.url ? { uri: ad.icon.url } : ad.icon;

  return (
    <PressableStamp
      onPress={onPress}
      stampOffset={4}
      borderRadius={16}
      borderColor={COLORS.ink}
      borderWidth={2}
      style={styles.card}
    >
      {/* Top row: brand + Sponsored badge (mirrors EventCard's date/time row) */}
      <View style={styles.topRow}>
        <View style={styles.brandRow}>
          <Image source={iconSource} style={styles.brandDot} resizeMode="cover" />
          <Text style={styles.advertiser} numberOfLines={1}>
            {ad.advertiser}
          </Text>
        </View>
        <AdBadge />
      </View>

      {/* Headline (mirrors occasion) */}
      <Text style={styles.headline} numberOfLines={1}>
        {ad.headline}
      </Text>

      {/* Body (mirrors venue row) */}
      <View style={styles.bodyRow}>
        <Ionicons name="sparkles-outline" size={14} color={COLORS.textMuted} />
        <Text style={styles.bodyText} numberOfLines={1}>
          {ad.body}
        </Text>
      </View>

      {/* CTA chip (mirrors the person chips) */}
      <View style={styles.ctaChip}>
        <Text style={styles.ctaText}>{ad.callToAction}</Text>
        <Ionicons name="arrow-forward" size={12} color="#FFFFFF" />
      </View>
    </PressableStamp>
  );
}

const styles = StyleSheet.create({
  card: { padding: 14, marginBottom: 12, backgroundColor: COLORS.card },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 1 },
  brandDot: {
    width: 28,
    height: 28,
    borderRadius: 8,
  },
  advertiser: { fontSize: 14, fontWeight: "700", color: COLORS.textPrimary },
  headline: { fontSize: 17, fontWeight: "600", color: COLORS.textPrimary, marginBottom: 6 },
  bodyRow: { flexDirection: "row", alignItems: "center", gap: 5, marginBottom: 8 },
  bodyText: { fontSize: 13, color: COLORS.textSecondary, flex: 1 },
  ctaChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    alignSelf: "flex-start",
    backgroundColor: COLORS.accent,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 999,
  },
  ctaText: { fontSize: 12, fontWeight: "700", color: "#FFFFFF" },
});
