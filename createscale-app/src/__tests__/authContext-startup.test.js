/**
 * Additional coverage — AuthProvider startup flow.
 *
 * The startup logic in AuthContext.js decides whether to keep or clear
 * a stored token based on the fetchAuthMe response:
 *   - 200 → keep token, set user
 *   - 401 → clear token (force re-login)
 *   - network error → keep token (don't punish transient failures)
 *
 * Run: npm test -- authContext-startup
 */

import React, { useContext } from "react";
import { Text } from "react-native";
import { render, screen, act, waitFor } from "@testing-library/react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { loginWithUsernamePassword, fetchAuthMe } from "../api/auth";
import { AuthProvider, AuthContext } from "../context/AuthContext";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("@react-native-async-storage/async-storage", () => ({
    getItem: jest.fn(),
    setItem: jest.fn(),
    removeItem: jest.fn(),
}));

jest.mock("../api/auth", () => ({
    loginWithUsernamePassword: jest.fn(),
    fetchAuthMe: jest.fn(),
}));

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

let capturedCtx = null;

function TestConsumer() {
    const ctx = useContext(AuthContext);
    capturedCtx = ctx;
    return (
        <>
            <Text testID="token">{String(ctx.token ?? "NULL")}</Text>
            <Text testID="user">{ctx.user ? ctx.user.username : "NULL"}</Text>
            <Text testID="initializing">{String(ctx.initializing)}</Text>
        </>
    );
}

// ---------------------------------------------------------------------------
// Startup flow
// ---------------------------------------------------------------------------

describe("AuthProvider startup", () => {
    beforeEach(() => {
        jest.clearAllMocks();
        capturedCtx = null;
    });

    test("no stored token → token stays null, initializing becomes false", async () => {
        AsyncStorage.getItem.mockResolvedValueOnce(null);

        render(<AuthProvider><TestConsumer /></AuthProvider>);

        await waitFor(() => {
            expect(screen.getByTestId("initializing").props.children).toBe("false");
        });
        expect(screen.getByTestId("token").props.children).toBe("NULL");
        expect(screen.getByTestId("user").props.children).toBe("NULL");
    });

    test("valid stored token → sets token and user from fetchAuthMe", async () => {
        AsyncStorage.getItem.mockResolvedValueOnce("good-token");
        fetchAuthMe.mockResolvedValueOnce({ user_id: 1, username: "anish" });

        render(<AuthProvider><TestConsumer /></AuthProvider>);

        await waitFor(() => {
            expect(screen.getByTestId("initializing").props.children).toBe("false");
        });
        expect(screen.getByTestId("token").props.children).toBe("good-token");
        expect(screen.getByTestId("user").props.children).toBe("anish");
    });

    test("stored token + 401 → clears token from AsyncStorage", async () => {
        AsyncStorage.getItem.mockResolvedValueOnce("stale-token");
        const err = new Error("Invalid token.");
        err.status = 401;
        fetchAuthMe.mockRejectedValueOnce(err);

        render(<AuthProvider><TestConsumer /></AuthProvider>);

        await waitFor(() => {
            expect(screen.getByTestId("initializing").props.children).toBe("false");
        });
        expect(AsyncStorage.removeItem).toHaveBeenCalledWith("@auth_token");
        expect(screen.getByTestId("token").props.children).toBe("NULL");
    });

    test("stored token + network error → keeps token, no forced logout", async () => {
        AsyncStorage.getItem.mockResolvedValueOnce("offline-token");
        const err = new Error("Network request failed");
        fetchAuthMe.mockRejectedValueOnce(err);

        render(<AuthProvider><TestConsumer /></AuthProvider>);

        await waitFor(() => {
            expect(screen.getByTestId("initializing").props.children).toBe("false");
        });
        expect(AsyncStorage.removeItem).not.toHaveBeenCalled();
        expect(screen.getByTestId("token").props.children).toBe("offline-token");
    });
});

// ---------------------------------------------------------------------------
// login() / logout()
// ---------------------------------------------------------------------------

describe("AuthProvider login and logout", () => {
    beforeEach(() => {
        jest.clearAllMocks();
        capturedCtx = null;
        AsyncStorage.getItem.mockResolvedValueOnce(null);
    });

    test("login() stores token and sets user", async () => {
        loginWithUsernamePassword.mockResolvedValueOnce({ token: "new-tok" });
        fetchAuthMe.mockResolvedValueOnce({ user_id: 2, username: "harsh" });

        render(<AuthProvider><TestConsumer /></AuthProvider>);

        await waitFor(() => expect(capturedCtx.initializing).toBe(false));

        await act(async () => {
            await capturedCtx.login("harsh", "password");
        });

        expect(AsyncStorage.setItem).toHaveBeenCalledWith("@auth_token", "new-tok");
        expect(capturedCtx.token).toBe("new-tok");
        expect(capturedCtx.user).toEqual({ user_id: 2, username: "harsh" });
    });

    test("logout() clears token, user, and AsyncStorage", async () => {
        AsyncStorage.getItem.mockReset();
        AsyncStorage.getItem.mockResolvedValueOnce("existing-tok");
        fetchAuthMe.mockResolvedValueOnce({ user_id: 1, username: "anish" });

        render(<AuthProvider><TestConsumer /></AuthProvider>);

        await waitFor(() => expect(capturedCtx.initializing).toBe(false));
        expect(capturedCtx.token).toBe("existing-tok");

        await act(async () => {
            await capturedCtx.logout();
        });

        expect(capturedCtx.token).toBe(null);
        expect(capturedCtx.user).toBe(null);
        expect(AsyncStorage.removeItem).toHaveBeenCalledWith("@auth_token");
    });
});
