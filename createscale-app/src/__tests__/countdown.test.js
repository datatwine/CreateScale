import { pad, computeCountdown } from "../utils/countdown";

// ---------------------------------------------------------------------------
// pad
// ---------------------------------------------------------------------------

describe("pad", () => {
    test("single digit is zero-padded", () => {
        expect(pad(0)).toBe("00");
        expect(pad(9)).toBe("09");
    });

    test("double digit is returned as-is", () => {
        expect(pad(10)).toBe("10");
        expect(pad(59)).toBe("59");
    });

    test("truncates decimals before padding", () => {
        // diff / 86400000 produces floats — pad must floor them
        expect(pad(1.9)).toBe("01");
        expect(pad(23.999)).toBe("23");
    });
});

// ---------------------------------------------------------------------------
// computeCountdown
// ---------------------------------------------------------------------------

describe("computeCountdown", () => {
    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    test("returns null for a date in the past", () => {
        jest.setSystemTime(new Date("2026-06-23T12:00:00Z"));
        const past = new Date("2026-06-22T12:00:00Z");
        expect(computeCountdown(past)).toBeNull();
    });

    test("returns null when target equals now", () => {
        jest.setSystemTime(new Date("2026-06-23T12:00:00Z"));
        expect(computeCountdown(new Date("2026-06-23T12:00:00Z"))).toBeNull();
    });

    test("returns correct days, hours, mins, secs for a future date", () => {
        // Fix clock to a known point
        jest.setSystemTime(new Date("2026-06-23T00:00:00Z"));
        // Target: exactly 2 days, 3 hours, 4 minutes, 5 seconds later
        const target = new Date("2026-06-25T03:04:05Z");

        const result = computeCountdown(target);

        expect(result).not.toBeNull();
        expect(result.days).toBe("02");
        expect(result.hours).toBe("03");
        expect(result.mins).toBe("04");
        expect(result.secs).toBe("05");
    });

    test("zero-pads all units", () => {
        jest.setSystemTime(new Date("2026-06-23T00:00:00Z"));
        const target = new Date("2026-06-23T00:01:01Z"); // 0d 0h 1m 1s

        const result = computeCountdown(target);

        expect(result.days).toBe("00");
        expect(result.hours).toBe("00");
        expect(result.mins).toBe("01");
        expect(result.secs).toBe("01");
    });

    test("returns object with exactly the four expected keys", () => {
        jest.setSystemTime(new Date("2026-06-23T00:00:00Z"));
        const target = new Date("2026-06-24T00:00:00Z");

        const result = computeCountdown(target);

        expect(Object.keys(result).sort()).toEqual(["days", "hours", "mins", "secs"]);
    });
});
