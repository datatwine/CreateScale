// src/screens/GlobalFeedScreen.js
//
// Displays a paginated feed of performer profiles with a profession
// pill-filter at the top.  Mirrors the Django global_feed view but
// styled for mobile with large photo cards (matching the dark-themed
// mockup the user approved).
//
// Backend endpoints used:
//   GET /api/users/professions/          → list of distinct professions
//   GET /api/users/feed/?profession=X&page=N → paginated profiles

import React, {
    useCallback,
    useContext,
    useEffect,
    useState,
} from "react";
import {
    ActivityIndicator,
    Alert,
    FlatList,
    Image,
    SafeAreaView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";

// ---------------------------------------------------------------------------
// Shared helpers (same logic as ProfileScreen — tiny, so duplicated here
// to keep the file self-contained until a shared utils.js is justified)
// ---------------------------------------------------------------------------

/** Build an absolute URL for API endpoints. */
function buildApiUrl(path) {
    const trimmedBase = API_BASE_URL.replace(/\/+$/, "");
    const trimmedPath = path.replace(/^\/+/, "");
    return `${trimmedBase}/${trimmedPath}`;
}

/**
 * Turn a relative or absolute media path into a usable URL for <Image>.
 * Handles "/media/..." paths from DRF running behind nginx.
 */
function makeMediaUrl(pathOrUrl) {
    if (!pathOrUrl) return null;
    if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
        return pathOrUrl;
    }
    const backendRoot = API_BASE_URL.replace(/\/api\/?$/, "");
    return pathOrUrl.startsWith("/")
        ? backendRoot + pathOrUrl
        : `${backendRoot}/${pathOrUrl}`;
}

// ---------------------------------------------------------------------------
// Color palette — mirrors ProfileScreen so the app feels cohesive
// ---------------------------------------------------------------------------

const COLORS = {
    background: "#0B0F1A",       // deep navy, close to the mockup
    card: "#141A2E",             // slightly lighter navy for cards
    cardOverlay: "rgba(0,0,0,0.55)",
    accent: "#E68A00",           // orange, consistent with ProfileScreen
    textPrimary: "#FFFFFF",
    textSecondary: "#CFCFCF",
    textMuted: "#8A8FA0",
    pillBg: "#1E2438",           // inactive filter pill
    pillActiveBg: "#E68A00",     // active filter pill
    divider: "#2B2B2B",
};

// ---------------------------------------------------------------------------
// FeedCard — one performer card matching the dark-photo-overlay design
// ---------------------------------------------------------------------------

function FeedCard({ profile, onPress }) {
    const imageUri = makeMediaUrl(profile.profile_picture_url);

    return (
        <TouchableOpacity
            style={styles.card}
            activeOpacity={0.85}
            onPress={onPress}
        >
            {/* Large profile photo — fills most of the card */}
            {imageUri ? (
                <Image
                    source={{ uri: imageUri }}
                    style={styles.cardImage}
                    resizeMode="cover"
                />
            ) : (
                // Fallback: initial letter on a dark background
                <View style={[styles.cardImage, styles.cardImagePlaceholder]}>
                    <Text style={styles.cardInitial}>
                        {(profile.username || "?").charAt(0).toUpperCase()}
                    </Text>
                </View>
            )}

            {/* Semi-transparent overlay with text at the bottom */}
            <View style={styles.cardOverlay}>
                <Text style={styles.cardName} numberOfLines={1}>
                    {profile.username}
                </Text>

                {profile.profession ? (
                    <Text style={styles.cardProfession} numberOfLines={1}>
                        {profile.profession}
                    </Text>
                ) : null}

                {profile.bio ? (
                    <Text style={styles.cardBio} numberOfLines={2}>
                        {profile.bio}
                    </Text>
                ) : null}
            </View>
        </TouchableOpacity>
    );
}

// ---------------------------------------------------------------------------
// ProfessionFilter — horizontal row of pill chips
// ---------------------------------------------------------------------------

function ProfessionFilter({ professions, selected, onSelect }) {
    return (
        <View style={styles.filterRow}>
            {/* "All" pill — clears the filter */}
            <TouchableOpacity
                style={[styles.pill, !selected && styles.pillActive]}
                onPress={() => onSelect(null)}
            >
                <Text style={[styles.pillText, !selected && styles.pillTextActive]}>
                    All
                </Text>
            </TouchableOpacity>

            {professions.map((p) => (
                <TouchableOpacity
                    key={p}
                    style={[styles.pill, selected === p && styles.pillActive]}
                    onPress={() => onSelect(p)}
                >
                    <Text
                        style={[styles.pillText, selected === p && styles.pillTextActive]}
                    >
                        {p}
                    </Text>
                </TouchableOpacity>
            ))}
        </View>
    );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function GlobalFeedScreen({ navigation }) {
    const { token } = useContext(AuthContext);

    // --- State ---------------------------------------------------------------
    const [professions, setProfessions] = useState([]);
    const [selectedProfession, setSelectedProfession] = useState(null);

    const [profiles, setProfiles] = useState([]);
    const [page, setPage] = useState(1);
    const [hasNext, setHasNext] = useState(false);
    const [loadingFeed, setLoadingFeed] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    // --- Data fetchers -------------------------------------------------------

    /** Fetch the distinct professions list (called once on mount). */
    const fetchProfessions = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(buildApiUrl("/users/professions/"), {
                headers: { Authorization: `Token ${token}`, Accept: "application/json" },
            });
            if (!res.ok) return;
            const data = await res.json();
            setProfessions(data.professions || []);
        } catch (err) {
            console.warn("Failed to load professions", err);
        }
    }, [token]);

    /**
     * Fetch a page of profiles, optionally filtered by profession.
     * @param {number} pageNum  - 1-based page index
     * @param {boolean} append  - true → append to existing list (pagination)
     */
    const fetchFeed = useCallback(
        async (pageNum = 1, append = false) => {
            if (!token) return;

            // Build query string
            let qs = `page=${pageNum}`;
            if (selectedProfession) qs += `&profession=${encodeURIComponent(selectedProfession)}`;

            try {
                const res = await fetch(buildApiUrl(`/users/feed/?${qs}`), {
                    headers: { Authorization: `Token ${token}`, Accept: "application/json" },
                });
                if (!res.ok) {
                    const text = await res.text();
                    console.warn("Feed load failed:", res.status, text);
                    return;
                }

                const data = await res.json();

                setProfiles((prev) => (append ? [...prev, ...data.results] : data.results));
                setPage(data.page);
                setHasNext(data.has_next);
            } catch (err) {
                console.error("Error loading feed", err);
                Alert.alert("Error", "Couldn't load the feed. Please try again.");
            }
        },
        [token, selectedProfession],
    );

    // --- Effects -------------------------------------------------------------

    // Load professions once on mount
    useEffect(() => {
        fetchProfessions();
    }, [fetchProfessions]);

    // Reload feed when filter changes (or on first mount)
    useEffect(() => {
        setLoadingFeed(true);
        fetchFeed(1, false).finally(() => setLoadingFeed(false));
    }, [fetchFeed]);

    // --- Handlers ------------------------------------------------------------

    /** Pull-to-refresh: reset to page 1 */
    const handleRefresh = async () => {
        setRefreshing(true);
        await fetchFeed(1, false);
        setRefreshing(false);
    };

    /** Infinite scroll: load next page when near the bottom */
    const handleLoadMore = async () => {
        if (!hasNext || loadingMore) return;
        setLoadingMore(true);
        await fetchFeed(page + 1, true);
        setLoadingMore(false);
    };

    /** Tapping a card → navigate to ProfileDetail (read-only view + hire) */
    const handleCardPress = (profile) => {
        navigation.navigate("ProfileDetail", { userId: profile.user_id });
    };


    // --- Render --------------------------------------------------------------

    const renderFooter = () => {
        if (!loadingMore) return null;
        return (
            <View style={styles.footerLoader}>
                <ActivityIndicator size="small" color={COLORS.accent} />
            </View>
        );
    };

    return (
        <SafeAreaView style={styles.safeArea}>
            {/* Header */}
            <View style={styles.header}>
                {/* Back arrow to ProfileScreen */}
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.backButton}
                >
                    <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
                </TouchableOpacity>

                <View>
                    <Text style={styles.headerTitle}>Performing Artists</Text>
                    <Text style={styles.headerSubtitle}>
                        Discover talented performers from around the world
                    </Text>
                </View>
            </View>

            {/* Profession filter pills */}
            {professions.length > 0 && (
                <ProfessionFilter
                    professions={professions}
                    selected={selectedProfession}
                    onSelect={setSelectedProfession}
                />
            )}

            {/* Feed list */}
            {loadingFeed ? (
                <View style={styles.centeredLoader}>
                    <ActivityIndicator size="large" color={COLORS.accent} />
                    <Text style={styles.loadingText}>Loading feed…</Text>
                </View>
            ) : (
                <FlatList
                    data={profiles}
                    keyExtractor={(item) => String(item.user_id)}
                    renderItem={({ item }) => (
                        <FeedCard
                            profile={item}
                            onPress={() => handleCardPress(item)}
                        />
                    )}
                    contentContainerStyle={styles.listContent}
                    showsVerticalScrollIndicator={false}
                    // Pull-to-refresh
                    refreshing={refreshing}
                    onRefresh={handleRefresh}
                    // Infinite scroll — fire when 20% from the bottom
                    onEndReached={handleLoadMore}
                    onEndReachedThreshold={0.2}
                    ListFooterComponent={renderFooter}
                    // Empty state
                    ListEmptyComponent={
                        <View style={styles.emptyState}>
                            <Text style={styles.emptyText}>
                                No performers found{selectedProfession ? ` for "${selectedProfession}"` : ""}.
                            </Text>
                        </View>
                    }
                />
            )}
        </SafeAreaView>
    );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
    safeArea: {
        flex: 1,
        backgroundColor: COLORS.background,
    },

    // --- Header ---
    header: {
        flexDirection: "row",
        alignItems: "center",
        paddingHorizontal: 16,
        paddingTop: 8,
        paddingBottom: 12,
    },
    backButton: {
        marginRight: 12,
        padding: 4,
    },
    headerTitle: {
        fontSize: 24,
        fontWeight: "700",
        color: COLORS.textPrimary,
    },
    headerSubtitle: {
        fontSize: 13,
        color: COLORS.textMuted,
        marginTop: 2,
    },

    // --- Filter pills ---
    filterRow: {
        flexDirection: "row",
        flexWrap: "wrap",
        gap: 8,
        paddingHorizontal: 16,
        paddingBottom: 12,
    },
    pill: {
        paddingHorizontal: 14,
        paddingVertical: 6,
        borderRadius: 999,
        backgroundColor: COLORS.pillBg,
    },
    pillActive: {
        backgroundColor: COLORS.pillActiveBg,
    },
    pillText: {
        fontSize: 13,
        fontWeight: "500",
        color: COLORS.textSecondary,
    },
    pillTextActive: {
        color: COLORS.textPrimary,
    },

    // --- Feed list ---
    listContent: {
        paddingHorizontal: 16,
        paddingBottom: 24,
    },

    // --- Card ---
    card: {
        borderRadius: 16,
        overflow: "hidden",
        backgroundColor: COLORS.card,
        marginBottom: 16,

        // Subtle shadow for depth
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 5,
    },
    cardImage: {
        width: "100%",
        height: 220,
    },
    cardImagePlaceholder: {
        backgroundColor: "#1A2040",
        alignItems: "center",
        justifyContent: "center",
    },
    cardInitial: {
        fontSize: 48,
        fontWeight: "700",
        color: COLORS.accent,
    },

    // Text overlay at the bottom of each card
    cardOverlay: {
        padding: 14,
        backgroundColor: COLORS.cardOverlay,
    },
    cardName: {
        fontSize: 18,
        fontWeight: "700",
        color: COLORS.textPrimary,
    },
    cardProfession: {
        fontSize: 14,
        color: COLORS.accent,
        marginTop: 2,
    },
    cardBio: {
        fontSize: 13,
        color: COLORS.textMuted,
        marginTop: 6,
        lineHeight: 18,
    },

    // --- Loaders & empty state ---
    centeredLoader: {
        flex: 1,
        justifyContent: "center",
        alignItems: "center",
    },
    loadingText: {
        marginTop: 8,
        color: COLORS.textSecondary,
        fontSize: 14,
    },
    footerLoader: {
        paddingVertical: 16,
        alignItems: "center",
    },
    emptyState: {
        marginTop: 40,
        alignItems: "center",
    },
    emptyText: {
        color: COLORS.textMuted,
        fontSize: 15,
    },
});
