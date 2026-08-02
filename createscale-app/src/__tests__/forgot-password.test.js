/**
 * Tests for forgotPassword() API client.
 *
 * Run: npm test -- forgot-password
 */

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));
jest.mock("@react-native-async-storage/async-storage", () => ({ getItem: jest.fn() }));

import { forgotPassword } from "../api/auth";

describe("forgotPassword", () => {
    beforeEach(() => {
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test("POSTs to /auth/forgot-password/ with the email", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ detail: "Password reset link sent to your email." }),
        });

        await forgotPassword("user@example.com");

        expect(global.fetch).toHaveBeenCalledWith(
            "http://localhost:8000/api/auth/forgot-password/",
            expect.objectContaining({
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: "user@example.com" }),
            }),
        );
    });

    test("returns data containing the detail message on success", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ detail: "Password reset link sent to your email." }),
        });

        const result = await forgotPassword("user@example.com");
        expect(result).toEqual({ detail: "Password reset link sent to your email." });
    });

    test("throws the backend detail message on 400", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: false,
            json: async () => ({ detail: "No account found with this email address." }),
        });

        await expect(forgotPassword("nobody@example.com"))
            .rejects.toThrow("No account found with this email address.");
    });

    test("throws a network error when fetch itself rejects", async () => {
        global.fetch.mockRejectedValueOnce(new TypeError("Network request failed"));

        await expect(forgotPassword("user@example.com"))
            .rejects.toThrow(/network request failed/i);
    });
});
