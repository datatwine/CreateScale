/**
 * Tests for the Settings drawer — pure helpers and component behaviour.
 *
 * TDD: these were written BEFORE the implementation.
 * Run:  npm test -- settingsDrawer
 */

import { maskAccountNumber, kycLabel, kycColor } from "../utils/settingsDrawer";

// ---------------------------------------------------------------------------
// maskAccountNumber
// ---------------------------------------------------------------------------

describe("maskAccountNumber", () => {
    test("masks all but the last 4 digits", () => {
        expect(maskAccountNumber("1234567890")).toBe("****7890");
    });

    test("returns empty string for null", () => {
        expect(maskAccountNumber(null)).toBe("");
    });

    test("returns empty string for empty string", () => {
        expect(maskAccountNumber("")).toBe("");
    });

    test("handles short numbers (4 digits or fewer) by showing all", () => {
        expect(maskAccountNumber("1234")).toBe("****1234");
    });
});

// ---------------------------------------------------------------------------
// kycLabel — human-readable status string
// ---------------------------------------------------------------------------

describe("kycLabel", () => {
    test("approved returns ready label", () => {
        expect(kycLabel("approved")).toBe("Approved — ready for payouts");
    });

    test("pending returns review label", () => {
        expect(kycLabel("pending")).toBe("Pending RBI review (5-7 days)");
    });

    test("rejected returns resubmit label", () => {
        expect(kycLabel("rejected")).toBe("Rejected — please re-submit");
    });

    test("null / not set returns setup prompt", () => {
        expect(kycLabel(null)).toBe("Not set up — clients cannot pay you");
        expect(kycLabel("")).toBe("Not set up — clients cannot pay you");
        expect(kycLabel(undefined)).toBe("Not set up — clients cannot pay you");
    });
});

// ---------------------------------------------------------------------------
// kycColor — badge colour per status (matches web CSS classes)
// ---------------------------------------------------------------------------

describe("kycColor", () => {
    test("approved is green", () => {
        expect(kycColor("approved")).toBe("green");
    });

    test("pending is amber", () => {
        expect(kycColor("pending")).toBe("amber");
    });

    test("rejected is red", () => {
        expect(kycColor("rejected")).toBe("red");
    });

    test("anything else is grey", () => {
        expect(kycColor(null)).toBe("grey");
        expect(kycColor("")).toBe("grey");
        expect(kycColor("unknown")).toBe("grey");
    });
});
