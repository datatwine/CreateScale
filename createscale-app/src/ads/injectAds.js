// createscale-app/src/ads/injectAds.js
//
// Interleave an ad object into a list of real items.
//   items       - real data (profiles or events)
//   ad          - the ad to insert, or null to insert nothing (not-ready / no-fill)
//   interval    - insert one ad after every `interval` real items
//   firstOffset - how many real items before the FIRST ad
// Returns a NEW array; never mutates `items`.

export function injectAds(items, ad, interval, firstOffset = interval) {
  if (!items?.length || !ad || interval < 1) return items || [];

  const out = [];
  let adCount = 0;

  for (let i = 0; i < items.length; i++) {
    out.push(items[i]);
    const pos = i + 1; // count of real items emitted so far (1-based)
    const isSlot =
      pos === firstOffset ||
      (pos > firstOffset && (pos - firstOffset) % interval === 0);
    if (isSlot) {
      out.push({ ...ad, id: `${ad.id}-${adCount++}` }); // unique per insertion
    }
  }
  return out;
}
