/**
 * TDD — written BEFORE implementation.
 *
 * fetchAuthMe must bound its request with a timeout so an unreachable
 * dev-LAN backend can't leave AuthContext's "Loading your session…"
 * screen hanging forever.
 *
 * Run: npm test -- auth
 */

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

import { fetchAuthMe } from "../api/auth";

describe("fetchAuthMe", () => {
    beforeEach(() => {
        jest.useFakeTimers();
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    test("resolves with user data on success", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ user_id: 1, username: "anish" }),
        });

        const result = await fetchAuthMe("tok123");
        expect(result).toEqual({ user_id: 1, username: "anish" });
    });

    test("attaches the HTTP status to the thrown error on failure", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            status: 401,
            json: async () => ({ detail: "Invalid token." }),
        });

        await expect(fetchAuthMe("stale-token")).rejects.toMatchObject({ status: 401 });
    });

    test("rejects instead of hanging when the backend never responds", async () => {
        global.fetch.mockImplementation((url, { signal } = {}) => {
            return new Promise((resolve, reject) => {
                signal?.addEventListener("abort", () => {
                    const err = new Error("Aborted");
                    err.name = "AbortError";
                    reject(err);
                });
            });
        });

        const promise = fetchAuthMe("tok123", 8000);
        const assertion = expect(promise).rejects.toThrow(/timed out/i);

        await jest.advanceTimersByTimeAsync(8000);
        await assertion;
    });
});
