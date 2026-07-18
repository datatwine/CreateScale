/**
 * TDD — written BEFORE implementation (issue #22).
 *
 * Tests for payment history utilities and screen module exports.
 * We test pure logic + fetch integration; we avoid full component
 * rendering because RNTL has known React 19 compatibility gaps in this project
 * (see settingsDrawer.test.js for the established pattern).
 *
 * Run: npm test -- paymentHistory
 */

// ---- module mocks (must be before any imports) ----------------------------

jest.mock("@react-native-async-storage/async-storage", () => ({
    getItem: jest.fn().mockResolvedValue("mock-token"),
}));

jest.mock("@react-navigation/native", () => ({
    useNavigation: () => ({ navigate: jest.fn(), goBack: jest.fn() }),
}));

jest.mock("react-native-safe-area-context", () => ({
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

// Real config/api.js's API_BASE_URL already ends in "/api" — mock must
// match that shape or a double "/api/api/..." bug goes undetected.
jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

global.fetch = jest.fn();

// ---------------------------------------------------------------------------
// Helpers imported by the screens (payment status → display color)
// ---------------------------------------------------------------------------

import { paymentStatusColor, paymentStatusLabel } from "../utils/paymentHistory";

describe("paymentStatusColor", () => {
    test("paid returns orange", () => {
        expect(paymentStatusColor("paid")).toBe("#E68A00");
    });

    test("released returns green", () => {
        expect(paymentStatusColor("released")).toBe("#2ecc71");
    });

    test("refunded returns red", () => {
        expect(paymentStatusColor("refunded")).toBe("#e74c3c");
    });

    test("unknown status returns grey", () => {
        expect(paymentStatusColor("unknown")).toBe("#aaa");
        expect(paymentStatusColor(null)).toBe("#aaa");
        expect(paymentStatusColor("")).toBe("#aaa");
    });
});

describe("paymentStatusLabel", () => {
    test("paid returns Paid (in escrow)", () => {
        expect(paymentStatusLabel("paid")).toBe("Paid (in escrow)");
    });

    test("released returns Released to performer", () => {
        expect(paymentStatusLabel("released")).toBe("Released to performer");
    });

    test("refunded returns Refunded to client", () => {
        expect(paymentStatusLabel("refunded")).toBe("Refunded to client");
    });

    test("unpaid / unknown returns Unpaid", () => {
        expect(paymentStatusLabel("unpaid")).toBe("Unpaid");
        expect(paymentStatusLabel(null)).toBe("Unpaid");
    });
});

// ---------------------------------------------------------------------------
// Screen module exports — screens must be importable with named exports
// ---------------------------------------------------------------------------

describe("PerformerPayoutsScreen module", () => {
    test("exports PerformerPayoutsScreen as a named export", () => {
        const mod = require("../screens/PerformerPayoutsScreen");
        expect(typeof mod.PerformerPayoutsScreen).toBe("function");
    });

    test("exports PerformerPayoutsScreen as default as well", () => {
        const mod = require("../screens/PerformerPayoutsScreen");
        expect(typeof mod.default).toBe("function");
    });
});

describe("ClientPaymentsScreen module", () => {
    test("exports ClientPaymentsScreen as a named export", () => {
        const mod = require("../screens/ClientPaymentsScreen");
        expect(typeof mod.ClientPaymentsScreen).toBe("function");
    });

    test("exports ClientPaymentsScreen as default as well", () => {
        const mod = require("../screens/ClientPaymentsScreen");
        expect(typeof mod.default).toBe("function");
    });
});

// ---------------------------------------------------------------------------
// Fetch URL contract — verify the screens call the right API endpoints
// ---------------------------------------------------------------------------

describe("PerformerPayoutsScreen fetch URL", () => {
    beforeEach(() => jest.clearAllMocks());

    test("calls /api/bookings/payouts/performer/ with auth token", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ count: 0, num_pages: 1, page: 1, has_next: false, has_previous: false, results: [] }),
        });

        // Import the fetch-wrapper util directly
        const { fetchPerformerPayouts } = require("../utils/paymentHistory");
        await fetchPerformerPayouts("test-token");

        expect(global.fetch).toHaveBeenCalledWith(
            "http://localhost:8000/api/bookings/payouts/performer/", // single /api, not /api/api
            expect.objectContaining({
                headers: expect.objectContaining({ Authorization: "Token test-token" }),
            }),
        );
    });

    test("unwraps the paginated response's results array", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                count: 1, num_pages: 1, page: 1, has_next: false, has_previous: false,
                results: [{ id: 1, fee: 5000 }],
            }),
        });

        const { fetchPerformerPayouts } = require("../utils/paymentHistory");
        const data = await fetchPerformerPayouts("test-token");

        expect(data).toEqual([{ id: 1, fee: 5000 }]);
    });
});

describe("ClientPaymentsScreen fetch URL", () => {
    beforeEach(() => jest.clearAllMocks());

    test("calls /api/bookings/payments/client/ with auth token", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ count: 0, num_pages: 1, page: 1, has_next: false, has_previous: false, results: [] }),
        });

        const { fetchClientPayments } = require("../utils/paymentHistory");
        await fetchClientPayments("test-token");

        expect(global.fetch).toHaveBeenCalledWith(
            "http://localhost:8000/api/bookings/payments/client/",
            expect.objectContaining({
                headers: expect.objectContaining({ Authorization: "Token test-token" }),
            }),
        );
    });

    test("unwraps the paginated response's results array", async () => {
        global.fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                count: 1, num_pages: 1, page: 1, has_next: false, has_previous: false,
                results: [{ id: 2, fee: 3000 }],
            }),
        });

        const { fetchClientPayments } = require("../utils/paymentHistory");
        const data = await fetchClientPayments("test-token");

        expect(data).toEqual([{ id: 2, fee: 3000 }]);
    });
});
