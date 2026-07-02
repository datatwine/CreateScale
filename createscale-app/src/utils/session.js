/** DRF returns 401 when the token is invalid/expired/deleted server-side. */
export function isUnauthorized(status) {
    return status === 401;
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
