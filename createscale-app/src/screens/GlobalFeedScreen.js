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
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";

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
// FeedCard — one performer card with stamp effect
// ---------------------------------------------------------------------------

function FeedCard({ profile, onPress }) {
    const imageUri = makeMediaUrl(profile.profile_picture_url);

    return (
        <PressableStamp
            onPress={onPress}
            stampOffset={4}
            stampOffsetY={5}
            borderRadius={14}
            borderColor={COLORS.ink}
            borderWidth={2}
            style={styles.card}
        >
            {imageUri ? (
                <Image
                    source={{ uri: imageUri }}
                    style={styles.cardAvatar}
                />
            ) : (
                <View style={[styles.cardAvatar, styles.cardAvatarPlaceholder]}>
                    <Text style={styles.cardInitial}>
                        {(profile.username || "?").charAt(0).toUpperCase()}
                    </Text>
                </View>
            )}

            <Text style={styles.cardName} numberOfLines={1}>
                {profile.username}
            </Text>

            {profile.profession ? (
                <View style={styles.professionPill}>
                    <Text style={styles.professionText} numberOfLines={1}>
                        {profile.profession}
                    </Text>
                </View>
            ) : null}
        </PressableStamp>
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
        <SafeAreaView style={styles.safeArea} edges={["top"]}>
            <View style={{ flex: 1, backgroundColor: COLORS.background }}>
            {/* Header */}
            <View style={styles.header}>

                <View style={styles.headerTextBlock}>
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
                    numColumns={2}
                    columnWrapperStyle={{ gap: 12 }}
                    renderItem={({ item }) => (
                        <View style={{ flex: 1, marginBottom: 12 }}>
                            <FeedCard
                                profile={item}
                                onPress={() => handleCardPress(item)}
                            />
                        </View>
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
            </View>
        </SafeAreaView>
    );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
    safeArea: {
        flex: 1,
        backgroundColor: "#000",
    },

    // --- Header ---
    header: {
        flexDirection: "row",
        alignItems: "center",
        paddingHorizontal: 16,
        paddingTop: 8,
        paddingBottom: 12,
    },
    headerTextBlock: {
        flexShrink: 1,
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
        backgroundColor: COLORS.cream,
    },
    pillActive: {
        backgroundColor: COLORS.accent,
    },
    pillText: {
        fontSize: 13,
        fontWeight: "500",
        color: COLORS.textSecondary,
    },
    pillTextActive: {
        color: COLORS.card,
    },

    // --- Feed list ---
    listContent: {
        paddingHorizontal: 16,
        paddingBottom: 24,
    },

    // --- Card ---
    card: {
        borderRadius: 14,
        backgroundColor: COLORS.card,
        alignItems: "center",
        padding: 16,
        height: 150,
    },
    cardAvatar: {
        width: 60,
        height: 60,
        borderRadius: 30,
        borderWidth: 2.5,
        borderColor: COLORS.accent,
        marginBottom: 10,
    },
    cardAvatarPlaceholder: {
        backgroundColor: COLORS.cream,
        alignItems: "center",
        justifyContent: "center",
    },
    cardInitial: {
        fontSize: 24,
        fontWeight: "700",
        color: COLORS.accent,
    },
    cardName: {
        fontSize: 15,
        fontWeight: "700",
        color: COLORS.textPrimary,
        textAlign: "center",
        marginBottom: 6,
    },
    professionPill: {
        backgroundColor: COLORS.cream,
        paddingHorizontal: 10,
        paddingVertical: 3,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: COLORS.divider,
    },
    professionText: {
        fontSize: 11,
        fontWeight: "600",
        color: COLORS.accent,
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
