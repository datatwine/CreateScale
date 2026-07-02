/**
 * TDD — written BEFORE implementation.
 *
 * Bug: a stale/invalid auth token left the user stuck on ProfileScreen
 * with a "couldn't load your profile" alert instead of being bounced
 * back to Login. Separately, the startup session check had no timeout,
 * so an unreachable dev-LAN backend made "Loading your session…" hang
 * indefinitely.
 *
 * Run: npm test -- session
 */

import { isUnauthorized, fetchWithTimeout } from "../utils/session";

// ---------------------------------------------------------------------------
// isUnauthorized
// ---------------------------------------------------------------------------

describe("isUnauthorized", () => {
    test("401 is unauthorized", () => {
        expect(isUnauthorized(401)).toBe(true);
    });

    test("200 is not unauthorized", () => {
        expect(isUnauthorized(200)).toBe(false);
    });

    test("403 (forbidden, not expired-token) is not unauthorized", () => {
        expect(isUnauthorized(403)).toBe(false);
    });

    test("500 is not unauthorized", () => {
        expect(isUnauthorized(500)).toBe(false);
    });

    test("undefined status is not unauthorized", () => {
        expect(isUnauthorized(undefined)).toBe(false);
    });
});

// ---------------------------------------------------------------------------
// fetchWithTimeout
// ---------------------------------------------------------------------------

describe("fetchWithTimeout", () => {
    beforeEach(() => {
        jest.useFakeTimers();
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    test("resolves normally when fetch settles before the timeout", async () => {
        const fakeResponse = { ok: true, status: 200 };
        global.fetch.mockResolvedValueOnce(fakeResponse);

        const result = await fetchWithTimeout("http://x/api/auth/me/", {}, 8000);

        expect(result).toBe(fakeResponse);
    });

    test("passes an AbortSignal through to the underlying fetch call", async () => {
        global.fetch.mockResolvedValueOnce({ ok: true, status: 200 });

        await fetchWithTimeout("http://x/api/auth/me/", { headers: { Authorization: "Token abc" } }, 8000);

        expect(global.fetch).toHaveBeenCalledWith(
            "http://x/api/auth/me/",
            expect.objectContaining({
                headers: { Authorization: "Token abc" },
                signal: expect.any(AbortSignal),
            }),
        );
    });

    test("rejects with a timeout error when fetch never settles", async () => {
        // fetch that hangs forever until aborted
        global.fetch.mockImplementation((url, { signal } = {}) => {
            return new Promise((resolve, reject) => {
                signal?.addEventListener("abort", () => {
                    const err = new Error("Aborted");
                    err.name = "AbortError";
                    reject(err);
                });
            });
        });

        const promise = fetchWithTimeout("http://x/api/auth/me/", {}, 5000);
        // Attach rejection handler immediately so Jest doesn't see an
        // "unhandled rejection" in the gap before timers advance.
        const assertion = expect(promise).rejects.toThrow(/timed out/i);

        await jest.advanceTimersByTimeAsync(5000);
        await assertion;
    });
});
