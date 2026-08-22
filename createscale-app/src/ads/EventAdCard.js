// createscale-app/src/ads/EventAdCard.js
//
// Dual-mode event ad card:
//   __DEV__ (Expo Go)  → mock ad from mockInventory (existing visuals)
//   Production build   → real AdMob NativeAd via the SDK
//
// Mirrors LiveEventsScreen's EventCard structure (top row, headline, body, CTA).
import React, { useEffect, useRef, useState } from "react";
import { View, Text, Image, StyleSheet, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";
import AdBadge from "./AdBadge";

let NativeAd, NativeAdView, NativeAsset, NativeAssetType;
let sdkAvailable = false;
try {
  const sdk = require("react-native-google-mobile-ads");
  NativeAd = sdk.NativeAd;
  NativeAdView = sdk.NativeAdView;
  NativeAsset = sdk.NativeAsset;
  NativeAssetType = sdk.NativeAssetType;
  sdkAvailable = true;
} catch {
  // SDK unavailable (Expo Go) — mock fallback used
}

function RealEventAd({ adUnitId }) {
  const [nativeAd, setNativeAd] = useState(null);
  const [error, setError] = useState(false);
  const adRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    NativeAd.createForAdRequest(adUnitId)
      .then((ad) => {
        if (cancelled) { ad.destroy(); return; }
        adRef.current = ad;
        setNativeAd(ad);
      })
      .catch(() => { if (!cancelled) setError(true); });

    return () => {
      cancelled = true;
      if (adRef.current) {
        adRef.current.destroy();
        adRef.current = null;
      }
    };
  }, [adUnitId]);

  if (error) return <View style={styles.card} />;

  if (!nativeAd) {
    return (
      <View style={[styles.card, styles.loadingCard]}>
        <ActivityIndicator size="small" color={COLORS.accent} />
      </View>
    );
  }

  return (
    <NativeAdView nativeAd={nativeAd} style={[styles.card, styles.realCard]}>
      <View style={styles.topRow}>
        <View style={styles.brandRow}>
          {nativeAd.icon?.url ? (
            <NativeAsset assetType={NativeAssetType.ICON}>
              <Image
                source={{ uri: nativeAd.icon.url }}
                style={styles.brandDot}
                resizeMode="cover"
              />
            </NativeAsset>
          ) : null}
          {nativeAd.advertiser ? (
            <NativeAsset assetType={NativeAssetType.ADVERTISER}>
              <Text style={styles.advertiser} numberOfLines={1}>
                {nativeAd.advertiser}
              </Text>
            </NativeAsset>
          ) : null}
        </View>
        <AdBadge />
      </View>

      <NativeAsset assetType={NativeAssetType.HEADLINE}>
        <Text style={styles.headline} numberOfLines={1}>
          {nativeAd.headline}
        </Text>
      </NativeAsset>

      <NativeAsset assetType={NativeAssetType.BODY}>
        <View style={styles.bodyRow}>
          <Ionicons name="sparkles-outline" size={14} color={COLORS.textMuted} />
          <Text style={styles.bodyText} numberOfLines={1}>
            {nativeAd.body}
          </Text>
        </View>
      </NativeAsset>

      <NativeAsset assetType={NativeAssetType.CALL_TO_ACTION}>
        <View style={styles.ctaChip}>
          <Text style={styles.ctaText}>{nativeAd.callToAction}</Text>
          <Ionicons name="arrow-forward" size={12} color="#FFFFFF" />
        </View>
      </NativeAsset>
    </NativeAdView>
  );
}

function MockEventAd({ ad, onPress }) {
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
      <View style={styles.topRow}>
        <View style={styles.brandRow}>
          <Image source={iconSource} style={styles.brandDot} resizeMode="cover" />
          <Text style={styles.advertiser} numberOfLines={1}>
            {ad.advertiser}
          </Text>
        </View>
        <AdBadge />
      </View>

      <Text style={styles.headline} numberOfLines={1}>
        {ad.headline}
      </Text>

      <View style={styles.bodyRow}>
        <Ionicons name="sparkles-outline" size={14} color={COLORS.textMuted} />
        <Text style={styles.bodyText} numberOfLines={1}>
          {ad.body}
        </Text>
      </View>

      <View style={styles.ctaChip}>
        <Text style={styles.ctaText}>{ad.callToAction}</Text>
        <Ionicons name="arrow-forward" size={12} color="#FFFFFF" />
      </View>
    </PressableStamp>
  );
}

export default function EventAdCard({ ad, onPress }) {
  if (ad.adUnitId && sdkAvailable) {
    return <RealEventAd adUnitId={ad.adUnitId} />;
  }
  return <MockEventAd ad={ad} onPress={onPress} />;
}

const styles = StyleSheet.create({
  card: { padding: 14, marginBottom: 12, backgroundColor: COLORS.card, borderRadius: 16 },
  realCard: {
    borderWidth: 2,
    borderColor: COLORS.ink,
  },
  loadingCard: {
    justifyContent: "center",
    alignItems: "center",
    minHeight: 120,
  },
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
