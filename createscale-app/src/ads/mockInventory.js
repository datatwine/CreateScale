// createscale-app/src/ads/mockInventory.js
//
// Simulated ads for VISUAL ITERATION ONLY. The field names below mirror the
// real NativeAd object from react-native-google-mobile-ads so the cards'
// property reads work identically against mocks and real ads.
//
// The ONE shape difference: `icon` here is a require() asset ID (renders
// from the bundle), while a real NativeAd's icon is { url, width, height }
// (renders from a remote URL). The cards handle both with a single ternary.

import CokeTile from "./assets/coke-tile.png";
import RedBullTile from "./assets/redbull-tile.png";

export const MOCK_FEED_AD = {
  // --- harness-only (ours, NOT part of AdMob's NativeAd) ---
  _isAd: true, // marks this item as an ad inside a data array
  id: "ad-coca-cola", // injection key

  // --- AdMob-faithful NativeAd fields ---
  headline: "Coca-Cola",
  body: "Taste the feeling",
  advertiser: "Coca-Cola",
  callToAction: "Learn More",
  icon: CokeTile, // require() asset — renders via <Image source={ad.icon} />
  images: null, // real shape: [{ url, width, height }, ...]. Not needed for icon-only cards.
};

export const MOCK_EVENT_AD = {
  _isAd: true,
  id: "ad-red-bull",

  headline: "Red Bull Gives You Wings",
  body: "Fuel your next performance",
  advertiser: "Red Bull",
  callToAction: "Discover More",
  icon: RedBullTile,
  images: null,
};
