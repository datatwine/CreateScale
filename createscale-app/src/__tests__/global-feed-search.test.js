/**
 * GlobalFeedScreen — feed search bar.
 *
 * The feed screen should:
 *   - render a search box above the profession pills
 *   - debounce typing (~300ms) then fetch /users/feed/ with ?search=<term>
 *   - show a clear (×) button while text is present, and tap it to reset to
 *     the unfiltered feed
 *
 * Run: npm test -- global-feed-search
 */

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

jest.mock("react-native-safe-area-context", () => {
    const React = require("react");
    const { View } = require("react-native");
    const SafeAreaView = (props) => React.createElement(View, props);
    return { SafeAreaView };
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { AuthContext } from "../context/AuthContext";
import GlobalFeedScreen from "../screens/GlobalFeedScreen";

const ALICE = {
    user_id: 2,
    username: "alice",
    profession: "Dancer",
    location: "Mumbai",
    profile_picture_url: null,
    is_performer: true,
    bio: "",
};
const BOB = {
    user_id: 3,
    username: "bob",
    profession: "Singer",
    location: "Delhi",
    profile_picture_url: null,
    is_performer: true,
    bio: "",
};

const PROFESSIONS = { professions: ["Dancer", "Singer"] };
const FULL_FEED = {
    count: 2,
    num_pages: 1,
    page: 1,
    has_next: false,
    has_previous: false,
    results: [ALICE, BOB],
};

let fetchCalls = null;

function mockFetch() {
    fetchCalls = [];
    global.fetch = jest.fn(async (url) => {
        const u = String(url);
        fetchCalls.push(u);
        const json = async () => {
            if (u.includes("/users/professions/")) return PROFESSIONS;

            // Search responses filtered the same way the backend does.
            if (u.includes("search=")) {
                const term = decodeURIComponent(
                    u.split("search=")[1].split("&")[0]
                ).toLowerCase();
                const results = [ALICE, BOB].filter(
                    (p) =>
                        p.username.toLowerCase().includes(term) ||
                        p.profession.toLowerCase().includes(term) ||
                        p.location.toLowerCase().includes(term)
                );
                return {
                    count: results.length,
                    num_pages: 1,
                    page: 1,
                    has_next: false,
                    has_previous: false,
                    results,
                };
            }

            return FULL_FEED;
        };
        return { ok: true, status: 200, json };
    });
}

async function renderScreen() {
    return render(
        <AuthContext.Provider value={{ token: "test-token" }}>
            <GlobalFeedScreen navigation={{ navigate: jest.fn() }} />
        </AuthContext.Provider>
    );
}

const SEARCH_PLACEHOLDER = "Search by name, profession, or city...";

// This working tree (WSL + expo) is very slow to compile the first screen,
// so the default 5s jest timeout / 1s waitFor timeout are too tight.
jest.setTimeout(120000);
const WAIT = { timeout: 20000, interval: 100 };

describe("GlobalFeedScreen search", () => {
    beforeEach(() => {
        mockFetch();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test("renders the search bar above the profession pills", async () => {
        await renderScreen();
        expect(await screen.findByPlaceholderText(SEARCH_PLACEHOLDER)).toBeTruthy();
        // Initial (unfiltered) feed loads
        await waitFor(() => expect(screen.getByText("alice")).toBeTruthy());
        expect(screen.getByText("bob")).toBeTruthy();
    });

    test("debounces typing and fetches with ?search=<term>", async () => {
        await renderScreen();
        const input = await screen.findByPlaceholderText(SEARCH_PLACEHOLDER);

        fireEvent.changeText(input, "ali");
        await waitFor(
            () => expect(fetchCalls.some((u) => u.includes("search=ali"))).toBe(true),
            WAIT
        );

        // Results are filtered to the matches only
        await waitFor(() => expect(screen.queryByText("bob")).toBeNull());
        expect(screen.getByText("alice")).toBeTruthy();
    });

    test("shows a clear button and resets to the full feed on tap", async () => {
        await renderScreen();
        const input = await screen.findByPlaceholderText(SEARCH_PLACEHOLDER);

        fireEvent.changeText(input, "mumbai");
        await waitFor(
            () => expect(fetchCalls.some((u) => u.includes("search=mumbai"))).toBe(true),
            WAIT
        );
        await waitFor(() => expect(screen.getByText("×")).toBeTruthy());

        fireEvent.press(screen.getByText("×"));
        await waitFor(
            () =>
                expect(
                    fetchCalls.some(
                        (u) => u.includes("/users/feed/") && !u.includes("search=")
                    )
                ).toBe(true),
            WAIT
        );

        // Full feed restored
        await waitFor(() => expect(screen.getByText("bob")).toBeTruthy());
        expect(input.props.value).toBe("");
    });

    test("empty search terms fetch the unfiltered feed", async () => {
        await renderScreen();
        const input = await screen.findByPlaceholderText(SEARCH_PLACEHOLDER);

        fireEvent.changeText(input, "   "); // whitespace-only → trimmed to ""
        await waitFor(() => expect(screen.getByText("bob")).toBeTruthy());

        const searchCalls = fetchCalls.filter((u) => u.includes("search="));
        expect(searchCalls.length).toBe(0);
    });
});