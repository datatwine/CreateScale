// createscale-app/src/ads/FeedAdCard.js
//
// Mirrors GlobalFeedScreen's FeedCard silhouette (avatar + name + pill) so it
// drops into the 2-column grid without breaking rhythm. Same PressableStamp
// wrapper, same card dimensions.
//
// Design note: the one deliberate visual difference from a performer card is
// the brand tile being a rounded square (not a circle) — a subtle cue that
// this is a brand, not a person — plus the "Sponsored" pill.
import React from "react";
import { View, Text, Image, StyleSheet } from "react-native";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";
import AdBadge from "./AdBadge";

export default function FeedAdCard({ ad, onPress }) {
  const iconSource = ad.icon?.url ? { uri: ad.icon.url } : ad.icon;

  return (
    <PressableStamp
      onPress={onPress}
      stampOffset={4}
      stampOffsetY={5}
      borderRadius={14}
      borderColor={COLORS.ink}
      borderWidth={2}
      style={styles.card}
    >
      <AdBadge style={styles.badge} />

      <Image source={iconSource} style={styles.brandTile} resizeMode="cover" />

      <Text style={styles.name} numberOfLines={1}>
        {ad.headline}
      </Text>

      <View style={styles.ctaPill}>
        <Text style={styles.ctaText} numberOfLines={1}>
          {ad.callToAction}
        </Text>
      </View>
    </PressableStamp>
  );
}

const styles = StyleSheet.create({
  // Matches FeedCard.styles.card exactly so grid cells line up.
  card: {
    borderRadius: 14,
    backgroundColor: COLORS.card, // #FFFFFF
    alignItems: "center",
    padding: 16,
    height: 150,
  },
  badge: { position: "absolute", top: 8, right: 8, zIndex: 2 },
  brandTile: {
    width: 60,
    height: 60,
    borderRadius: 14, // rounded-square = brand, vs circular avatar = person
    marginBottom: 10,
  },
  name: {
    fontSize: 15,
    fontWeight: "700",
    color: COLORS.textPrimary,
    textAlign: "center",
    marginBottom: 6,
  },
  ctaPill: {
    backgroundColor: COLORS.accent, // #E68A00
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 999,
  },
  ctaText: { fontSize: 11, fontWeight: "700", color: "#FFFFFF" },
});
