// createscale-app/src/ads/constants.js
//
// Placement tuning. "Interval" = how many real cards between ads.
// Lower = more ads. Start conservative; raise frequency after we see it live.

export const FEED_AD_INTERVAL = 6; // 2-col grid, ~8-10 cards/screen → ~1 ad/screen
export const FEED_FIRST_AD_OFFSET = 4; // first ad only after 4 real cards

export const EVENTS_AD_INTERVAL = 4; // 1-col, taller cards, ~3-4/screen → ~1 ad/screen
export const EVENTS_FIRST_AD_OFFSET = 3; // first ad only after 3 real events

// Google's test native ad unit ID — works without an AdMob account.
// Replace with real ad unit IDs after creating them in the AdMob dashboard.
export const ADMOB_NATIVE_AD_UNIT_ID = "ca-app-pub-3940256099942544/2247696110";
