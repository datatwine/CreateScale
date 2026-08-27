/**
 * TDD — written BEFORE implementation (issue #102).
 *
 * buildMediaSource turns an Upload record into the pre-resolved
 * { uri, isVideo, caption, id } shape MediaViewer consumes. It's the one bit
 * of branching logic (image vs video, which field, caption fallback) shared
 * by both profile screens, so it's tested in isolation with a fake resolver.
 *
 * Run: npm test -- mediaViewer.test
 */

import { buildMediaSource } from "../utils/mediaViewer";

// A resolver that just marks what it was given, so we can assert which field
// (and value) flowed through — mirrors makeMediaUrl's "null in → null out".
const resolve = (v) => (v ? `RESOLVED:${v}` : null);

describe("buildMediaSource", () => {
    test("returns null when there is no upload", () => {
        expect(buildMediaSource(null, resolve)).toBeNull();
        expect(buildMediaSource(undefined, resolve)).toBeNull();
    });

    test("returns null when the upload has neither image nor video", () => {
        expect(buildMediaSource({ id: 1, caption: "x" }, resolve)).toBeNull();
    });

    test("builds an image source (isVideo false)", () => {
        const out = buildMediaSource(
            { id: 3, image_url: "/media/a.jpg", caption: "hey" },
            resolve
        );
        expect(out).toEqual({
            uri: "RESOLVED:/media/a.jpg",
            isVideo: false,
            caption: "hey",
            id: 3,
        });
    });

    test("builds a video source (isVideo true) when only a video is present", () => {
        const out = buildMediaSource(
            { id: 4, video_url: "/media/clip.mp4" },
            resolve
        );
        expect(out).toEqual({
            uri: "RESOLVED:/media/clip.mp4",
            isVideo: true,
            caption: "",
            id: 4,
        });
    });

    test("prefers the image when both image and video are present", () => {
        const out = buildMediaSource(
            { id: 5, image_url: "/media/a.jpg", video_url: "/media/clip.mp4" },
            resolve
        );
        expect(out.uri).toBe("RESOLVED:/media/a.jpg");
        expect(out.isVideo).toBe(false);
    });

    test("falls back to the bare image/video fields when *_url is absent", () => {
        const img = buildMediaSource({ id: 6, image: "/media/b.jpg" }, resolve);
        expect(img.uri).toBe("RESOLVED:/media/b.jpg");
        expect(img.isVideo).toBe(false);

        const vid = buildMediaSource({ id: 7, video: "/media/d.mov" }, resolve);
        expect(vid.uri).toBe("RESOLVED:/media/d.mov");
        expect(vid.isVideo).toBe(true);
    });

    test("defaults a missing caption to an empty string", () => {
        const out = buildMediaSource({ id: 8, image_url: "/media/a.jpg" }, resolve);
        expect(out.caption).toBe("");
    });
});
