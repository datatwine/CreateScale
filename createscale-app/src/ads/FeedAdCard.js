// createscale-app/src/ads/FeedAdCard.js
//
// Dual-mode feed ad card:
//   __DEV__ (Expo Go)  → mock ad from mockInventory (existing visuals)
//   Production build   → real AdMob NativeAd via the SDK
//
// Both modes share the same card dimensions so the 2-column grid stays aligned.
import React, { useEffect, useRef, useState } from "react";
import { View, Text, Image, StyleSheet, ActivityIndicator } from "react-native";
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

function RealFeedAd({ adUnitId }) {
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
      <AdBadge style={styles.badge} />

      {nativeAd.icon?.url ? (
        <NativeAsset assetType={NativeAssetType.ICON}>
          <Image
            source={{ uri: nativeAd.icon.url }}
            style={styles.brandTile}
            resizeMode="cover"
          />
        </NativeAsset>
      ) : null}

      <NativeAsset assetType={NativeAssetType.HEADLINE}>
        <Text style={styles.name} numberOfLines={1}>
          {nativeAd.headline}
        </Text>
      </NativeAsset>

      <NativeAsset assetType={NativeAssetType.CALL_TO_ACTION}>
        <View style={styles.ctaPill}>
          <Text style={styles.ctaText} numberOfLines={1}>
            {nativeAd.callToAction}
          </Text>
        </View>
      </NativeAsset>
    </NativeAdView>
  );
}

function MockFeedAd({ ad, onPress }) {
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

export default function FeedAdCard({ ad, onPress }) {
  if (ad.adUnitId && sdkAvailable) {
    return <RealFeedAd adUnitId={ad.adUnitId} />;
  }
  return <MockFeedAd ad={ad} onPress={onPress} />;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    backgroundColor: COLORS.card,
    alignItems: "center",
    padding: 16,
    height: 150,
  },
  realCard: {
    borderWidth: 2,
    borderColor: COLORS.ink,
  },
  loadingCard: {
    justifyContent: "center",
  },
  badge: { position: "absolute", top: 8, right: 8, zIndex: 2 },
  brandTile: {
    width: 60,
    height: 60,
    borderRadius: 14,
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
    backgroundColor: COLORS.accent,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 999,
  },
  ctaText: { fontSize: 11, fontWeight: "700", color: "#FFFFFF" },
});
