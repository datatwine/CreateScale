import AsyncStorage from "@react-native-async-storage/async-storage";

/** DRF returns 401 when the token is invalid/expired/deleted server-side. */
export function isUnauthorized(status) {
    return status === 401;
}

/**
 * Single source of truth for the AsyncStorage key AuthContext stores the
 * DRF token under. Any screen reading its own token must use this so it
 * can't silently drift out of sync with AuthContext and send a null token.
 */
export const AUTH_TOKEN_KEY = "@auth_token";

export async function getStoredToken() {
    return AsyncStorage.getItem(AUTH_TOKEN_KEY);
}

/**
 * fetch() with a hard timeout. Without this, a stale dev-LAN IP or an
 * unreachable backend leaves the caller's promise pending indefinitely.
 */
export async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(url, { ...options, signal: controller.signal });
    } catch (err) {
        if (err.name === "AbortError") {
            throw new Error(`Request timed out after ${timeoutMs}ms`);
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}
