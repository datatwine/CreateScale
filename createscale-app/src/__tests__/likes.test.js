/**
 * TDD — written BEFORE implementation (issue #99).
 *
 * toggleLike wraps POST /api/users/profiles/<user_id>/like/ — the same
 * endpoint the website's heart button calls (session auth there, token
 * auth here). One call does both like and unlike; the server decides
 * which based on whether a Like row already exists.
 *
 * Run: npm test -- likes
 */

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

global.fetch = jest.fn();

import { toggleLike } from "../utils/likes";

describe("toggleLike", () => {
    beforeEach(() => jest.clearAllMocks());

    test("POSTs to /api/users/profiles/<user_id>/like/ with auth token", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ liked_by_me: true, likes_count: 1 }),
        });

        await toggleLike("test-token", 42);

        expect(global.fetch).toHaveBeenCalledWith(
            "http://localhost:8000/api/users/profiles/42/like/",
            expect.objectContaining({
                method: "POST",
                headers: expect.objectContaining({ Authorization: "Token test-token" }),
            })
        );
    });

    test("returns liked_by_me and likes_count from the response", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ liked_by_me: false, likes_count: 0 }),
        });

        const data = await toggleLike("test-token", 42);

        expect(data).toEqual({ liked_by_me: false, likes_count: 0 });
    });

    test("throws with the server's error message on failure", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            status: 400,
            json: async () => ({ detail: "You cannot like your own profile." }),
        });

        await expect(toggleLike("test-token", 42)).rejects.toMatchObject({
            message: "You cannot like your own profile.",
            status: 400,
        });
    });
});
