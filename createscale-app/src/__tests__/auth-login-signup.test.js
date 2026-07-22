/**
 * Additional coverage — loginWithUsernamePassword & signupWithCredentials
 * had zero tests. These follow the same mock pattern as auth.test.js.
 *
 * Run: npm test -- auth-login-signup
 */

import { loginWithUsernamePassword, signupWithCredentials } from "../api/auth";

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));
jest.mock("@react-native-async-storage/async-storage", () => ({ getItem: jest.fn() }));

// ---------------------------------------------------------------------------
// loginWithUsernamePassword
// ---------------------------------------------------------------------------

describe("loginWithUsernamePassword", () => {
    beforeEach(() => {
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test("POSTs to /auth/token/ with username and password", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: "abc123" }),
        });

        await loginWithUsernamePassword("anish", "pass123");

        expect(global.fetch).toHaveBeenCalledWith(
            "http://localhost:8000/api/auth/token/",
            expect.objectContaining({
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: "anish", password: "pass123" }),
            }),
        );
    });

    test("returns data containing the token on success", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: "abc123" }),
        });

        const result = await loginWithUsernamePassword("anish", "pass123");
        expect(result).toEqual({ token: "abc123" });
    });

    test("throws the backend detail message on 400", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            json: async () => ({ detail: "Unable to log in with provided credentials." }),
        });

        await expect(loginWithUsernamePassword("anish", "wrong"))
            .rejects.toThrow("Unable to log in with provided credentials.");
    });

    test("throws when the response has no token field", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ user_id: 1 }),
        });

        await expect(loginWithUsernamePassword("anish", "pass123"))
            .rejects.toThrow(/did not contain a token/i);
    });

    test("throws a network error when fetch itself rejects", async () => {
        global.fetch.mockRejectedValueOnce(new TypeError("Network request failed"));

        await expect(loginWithUsernamePassword("anish", "pass123"))
            .rejects.toThrow(/network request failed/i);
    });
});

// ---------------------------------------------------------------------------
// signupWithCredentials
// ---------------------------------------------------------------------------

describe("signupWithCredentials", () => {
    beforeEach(() => {
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test("POSTs to /auth/signup/ with all four fields", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: "new-tok", user_id: 7, username: "newuser" }),
        });

        await signupWithCredentials({
            username: "newuser",
            email: "new@example.com",
            password1: "Str0ng!",
            password2: "Str0ng!",
        });

        expect(global.fetch).toHaveBeenCalledWith(
            "http://localhost:8000/api/auth/signup/",
            expect.objectContaining({
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: "newuser",
                    email: "new@example.com",
                    password1: "Str0ng!",
                    password2: "Str0ng!",
                }),
            }),
        );
    });

    test("returns token, user_id, username on success", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: "new-tok", user_id: 7, username: "newuser" }),
        });

        const result = await signupWithCredentials({
            username: "newuser",
            email: "new@example.com",
            password1: "Str0ng!",
            password2: "Str0ng!",
        });

        expect(result).toEqual({ token: "new-tok", user_id: 7, username: "newuser" });
    });

    test("flattens DRF field errors into a readable message", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            json: async () => ({
                username: ["A user with that username already exists."],
                email: ["Enter a valid email address."],
            }),
        });

        await expect(
            signupWithCredentials({
                username: "taken",
                email: "bad",
                password1: "x",
                password2: "x",
            }),
        ).rejects.toThrow(/username:.*already exists/i);
    });

    test("throws when the response has no token field", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ user_id: 7 }),
        });

        await expect(
            signupWithCredentials({
                username: "u",
                email: "e@e.com",
                password1: "p",
                password2: "p",
            }),
        ).rejects.toThrow(/did not contain a token/i);
    });

    test("throws a network error when fetch itself rejects", async () => {
        global.fetch.mockRejectedValueOnce(new TypeError("Network request failed"));

        await expect(
            signupWithCredentials({
                username: "u",
                email: "e@e.com",
                password1: "p",
                password2: "p",
            }),
        ).rejects.toThrow(/network request failed/i);
    });
});
