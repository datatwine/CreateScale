/** Zero-pad a number to 2 digits. */
export function pad(n) {
    return String(Math.floor(n)).padStart(2, "0");
}

/**
 * Compute countdown parts from a target Date.
 * Returns { days, hours, mins, secs } strings, or null if the target is in the past.
 */
export function computeCountdown(targetDate) {
    const diff = targetDate - Date.now();
    if (diff <= 0) return null;
    return {
        days:  pad(diff / 86400000),
        hours: pad((diff % 86400000) / 3600000),
        mins:  pad((diff % 3600000) / 60000),
        secs:  pad((diff % 60000) / 1000),
    };
}
