/**
 * TDD — written BEFORE implementation (issue #78).
 *
 * injectAds is a pure function that interleaves an ad object into a list
 * of real items at a fixed interval. Two properties matter most:
 *   - ad = null returns the list unchanged (this is how "not ready yet" /
 *     "no-fill" naturally renders nothing, once real AdMob lands).
 *   - never mutates the input array.
 *
 * Run: npm test -- injectAds
 */

import { injectAds } from "../ads/injectAds";

const AD = { id: "ad-test", _isAd: true, headline: "Test Ad" };

describe("injectAds", () => {
    test("returns items unchanged when ad is null (not-ready / no-fill)", () => {
        const items = [{ id: 1 }, { id: 2 }, { id: 3 }];
        const result = injectAds(items, null, 2);
        expect(result).toEqual(items);
    });

    test("returns items unchanged when ad is undefined", () => {
        const items = [{ id: 1 }, { id: 2 }];
        const result = injectAds(items, undefined, 2);
        expect(result).toEqual(items);
    });

    test("returns empty array when items is empty", () => {
        expect(injectAds([], AD, 2)).toEqual([]);
    });

    test("returns empty array when items is null", () => {
        expect(injectAds(null, AD, 2)).toEqual([]);
    });

    test("returns items unchanged when interval is less than 1", () => {
        const items = [{ id: 1 }, { id: 2 }];
        expect(injectAds(items, AD, 0)).toEqual(items);
    });

    test("does not mutate the input array", () => {
        const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];
        const original = [...items];
        injectAds(items, AD, 2);
        expect(items).toEqual(original);
    });

    test("inserts one ad at firstOffset when firstOffset equals interval", () => {
        const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];
        const result = injectAds(items, AD, 2);
        // firstOffset defaults to interval (2): ad goes after item 2, then item 4.
        expect(result.map((i) => i._isAd ? "AD" : i.id)).toEqual([1, 2, "AD", 3, 4, "AD"]);
    });

    test("respects a custom firstOffset different from interval", () => {
        const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }, { id: 6 }, { id: 7 }];
        // firstOffset=3, then every 4 after that: slot at pos 3, next at pos 7.
        const result = injectAds(items, AD, 4, 3);
        expect(result.map((i) => i._isAd ? "AD" : i.id)).toEqual([1, 2, 3, "AD", 4, 5, 6, 7, "AD"]);
    });

    test("does not insert a trailing ad if list ends before the next slot", () => {
        const items = [{ id: 1 }, { id: 2 }, { id: 3 }];
        const result = injectAds(items, AD, 5, 5);
        // Only 3 items, slot is at position 5 — never reached.
        expect(result.map((i) => i._isAd ? "AD" : i.id)).toEqual([1, 2, 3]);
    });

    test("each inserted ad gets a unique id so keyExtractor never collides", () => {
        const items = Array.from({ length: 10 }, (_, i) => ({ id: i + 1 }));
        const result = injectAds(items, AD, 3, 3);
        const adIds = result.filter((i) => i._isAd).map((i) => i.id);
        expect(new Set(adIds).size).toBe(adIds.length);
        expect(adIds.length).toBeGreaterThan(1);
        adIds.forEach((id) => expect(id).toMatch(/^ad-test-\d+$/));
    });

    test("inserted ad objects preserve all original ad fields", () => {
        const items = [{ id: 1 }, { id: 2 }];
        const result = injectAds(items, AD, 1, 1);
        const inserted = result.find((i) => i._isAd);
        expect(inserted.headline).toBe("Test Ad");
        expect(inserted._isAd).toBe(true);
    });

    test("matches the Feed defaults (interval=6, firstOffset=4) shape", () => {
        const items = Array.from({ length: 12 }, (_, i) => ({ id: i + 1 }));
        const result = injectAds(items, AD, 6, 4);
        const adPositions = result
            .map((item, idx) => (item._isAd ? idx : null))
            .filter((idx) => idx !== null);
        // First ad after 4 real items (index 4), next after 6 more real items.
        expect(adPositions).toEqual([4, 11]);
    });
});
