// src/screens/LiveEventsScreen.js
//
// Shows accepted future (and optionally past) engagements.
//
// Backend endpoint:
//   GET /api/users/live-events/?page=N              → upcoming (default)
//   GET /api/users/live-events/?scope=past&page=N   → past (reverse-chrono)
//
// This is a read-only screen — events shown here are already accepted,
// so no action buttons are needed (use BookingsScreen for that).

import React, {
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
} from "react";
import {
    ActivityIndicator,
    Animated,
    FlatList,
    RefreshControl,
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
// Helpers
// ---------------------------------------------------------------------------

function buildApiUrl(path) {
    const base = API_BASE_URL.replace(/\/+$/, "");
    const rel = path.replace(/^\/+/, "");
    return `${base}/${rel}`;
}

/** Friendly date formatting — "12 Feb 2026" style */
function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr + "T00:00:00"); // avoid timezone shift
    const months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/** Friendly time formatting — "14:30" from "14:30:00" */
function formatTime(timeStr) {
    if (!timeStr) return "";
    return timeStr.slice(0, 5); // "HH:MM"
}

// ---------------------------------------------------------------------------
// Color palette — consistent with BookingsScreen / ProfileScreen
// ---------------------------------------------------------------------------

const COLORS = {
    background: "#0B0F1A",
    card: "#141A2E",
    cardPast: "#0F1220",       // slightly dimmer for past events
    accent: "#E68A00",
    accentDim: "#A36200",
    textPrimary: "#FFFFFF",
    textSecondary: "#CFCFCF",
    textMuted: "#8A8FA0",
    textDimmed: "#5A5F70",     // for past events
    divider: "#2B2B2B",
    liveGreen: "#2E7D32",
    pastGrey: "#424242",
    tabActive: "#E68A00",
    tabInactive: "#2A2A3A",
};

// ---------------------------------------------------------------------------
// EventCard — one event row (used for both upcoming and past)
// ---------------------------------------------------------------------------

function EventCard({ event, isPast }) {
    const cardBg = isPast ? COLORS.cardPast : COLORS.card;
    const textColor = isPast ? COLORS.textDimmed : COLORS.textSecondary;
    const titleColor = isPast ? COLORS.textMuted : COLORS.textPrimary;

    return (
        <View style={[styles.card, { backgroundColor: cardBg }]}>
            {/* Date + time row */}
            <View style={styles.cardTopRow}>
                <View style={styles.dateBlock}>
                    <Ionicons
                        name="calendar"
                        size={16}
                        color={isPast ? COLORS.textDimmed : COLORS.accent}
                    />
                    <Text style={[styles.dateText, { color: titleColor }]}>
                        {formatDate(event.date)}
                    </Text>
                </View>
                <View style={styles.timeBlock}>
                    <Ionicons
                        name="time-outline"
                        size={14}
                        color={textColor}
                    />
                    <Text style={[styles.timeText, { color: textColor }]}>
                        {formatTime(event.time)}
                    </Text>
                </View>
            </View>

            {/* Occasion */}
            <Text style={[styles.occasion, { color: titleColor }]} numberOfLines={1}>
                {event.occasion}
            </Text>

            {/* Venue */}
            <View style={styles.detailRow}>
                <Ionicons name="location-outline" size={14} color={textColor} />
                <Text style={[styles.detailText, { color: textColor }]} numberOfLines={1}>
                    {event.venue}
                </Text>
            </View>

            {/* People row */}
            <View style={styles.peopleRow}>
                <View style={styles.personChip}>
                    <Ionicons name="mic-outline" size={12} color={COLORS.accent} />
                    <Text style={[styles.personText, { color: textColor }]}>
                        {event.performer?.username}
                    </Text>
                </View>
                <View style={styles.personChip}>
                    <Ionicons name="person-outline" size={12} color={COLORS.textMuted} />
                    <Text style={[styles.personText, { color: textColor }]}>
                        {event.client?.username}
                    </Text>
                </View>
            </View>

            {/* Status pill */}
            {isPast && (
                <View style={[styles.statusPill, { backgroundColor: COLORS.pastGrey }]}>
                    <Text style={styles.statusPillText}>Completed</Text>
                </View>
            )}
        </View>
    );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function LiveEventsScreen({ navigation }) {
    const { token } = useContext(AuthContext);

    // "upcoming" or "past"
    const [scope, setScope] = useState("upcoming");

    // Data for each scope is tracked independently so switching is instant
    // after the first load.
    const [upcomingData, setUpcomingData] = useState([]);
    const [upcomingPage, setUpcomingPage] = useState(1);
    const [upcomingHasMore, setUpcomingHasMore] = useState(true);
    const [upcomingCount, setUpcomingCount] = useState(0);

    const [pastData, setPastData] = useState([]);
    const [pastPage, setPastPage] = useState(1);
    const [pastHasMore, setPastHasMore] = useState(true);
    const [pastCount, setPastCount] = useState(0);

    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);

    // Animated underline for the tab indicator
    const tabAnim = useRef(new Animated.Value(0)).current;

    // -----------------------------------------------------------------------
    // Fetch helper
    // -----------------------------------------------------------------------

    const fetchEvents = useCallback(
        async (fetchScope, page = 1) => {
            if (!token) return null;

            const scopeParam = fetchScope === "past" ? "&scope=past" : "";
            const url = buildApiUrl(`/users/live-events/?page=${page}${scopeParam}`);

            const res = await fetch(url, {
                headers: {
                    Authorization: `Token ${token}`,
                    Accept: "application/json",
                },
            });

            if (!res.ok) {
                const txt = await res.text();
                console.warn("LiveEvents fetch failed:", res.status, txt);
                return null;
            }

            return res.json();
        },
        [token],
    );

    // -----------------------------------------------------------------------
    // Initial load for both scopes
    // -----------------------------------------------------------------------

    useEffect(() => {
        let cancelled = false;

        (async () => {
            setLoading(true);

            // Fetch page 1 of both scopes concurrently
            const [upRes, pastRes] = await Promise.all([
                fetchEvents("upcoming", 1),
                fetchEvents("past", 1),
            ]);

            if (cancelled) return;

            if (upRes) {
                setUpcomingData(upRes.results);
                setUpcomingHasMore(upRes.has_next);
                setUpcomingPage(1);
                setUpcomingCount(upRes.count);
            }
            if (pastRes) {
                setPastData(pastRes.results);
                setPastHasMore(pastRes.has_next);
                setPastPage(1);
                setPastCount(pastRes.count);
            }

            setLoading(false);
        })();

        return () => { cancelled = true; };
    }, [fetchEvents]);

    // -----------------------------------------------------------------------
    // Refresh (pull-to-refresh)
    // -----------------------------------------------------------------------

    const handleRefresh = useCallback(async () => {
        setRefreshing(true);

        const [upRes, pastRes] = await Promise.all([
            fetchEvents("upcoming", 1),
            fetchEvents("past", 1),
        ]);

        if (upRes) {
            setUpcomingData(upRes.results);
            setUpcomingHasMore(upRes.has_next);
            setUpcomingPage(1);
            setUpcomingCount(upRes.count);
        }
        if (pastRes) {
            setPastData(pastRes.results);
            setPastHasMore(pastRes.has_next);
            setPastPage(1);
            setPastCount(pastRes.count);
        }

        setRefreshing(false);
    }, [fetchEvents]);

    // -----------------------------------------------------------------------
    // Infinite scroll — load next page
    // -----------------------------------------------------------------------

    const handleLoadMore = useCallback(async () => {
        const isUpcoming = scope === "upcoming";
        const hasMore = isUpcoming ? upcomingHasMore : pastHasMore;
        const currentPage = isUpcoming ? upcomingPage : pastPage;

        if (!hasMore || loadingMore) return;

        setLoadingMore(true);
        const nextPage = currentPage + 1;
        const res = await fetchEvents(scope, nextPage);

        if (res) {
            if (isUpcoming) {
                setUpcomingData((prev) => [...prev, ...res.results]);
                setUpcomingHasMore(res.has_next);
                setUpcomingPage(nextPage);
            } else {
                setPastData((prev) => [...prev, ...res.results]);
                setPastHasMore(res.has_next);
                setPastPage(nextPage);
            }
        }

        setLoadingMore(false);
    }, [scope, upcomingHasMore, pastHasMore, upcomingPage, pastPage, loadingMore, fetchEvents]);

    // -----------------------------------------------------------------------
    // Tab switching with animation
    // -----------------------------------------------------------------------

    const switchTab = (newScope) => {
        if (newScope === scope) return;
        setScope(newScope);
        Animated.spring(tabAnim, {
            toValue: newScope === "past" ? 1 : 0,
            useNativeDriver: true,
            friction: 8,
        }).start();
    };

    // -----------------------------------------------------------------------
    // Derived data
    // -----------------------------------------------------------------------

    const data = scope === "upcoming" ? upcomingData : pastData;
    const isPast = scope === "past";

    // -----------------------------------------------------------------------
    // Render helpers
    // -----------------------------------------------------------------------

    const renderItem = ({ item }) => (
        <EventCard event={item} isPast={isPast} />
    );

    const renderFooter = () => {
        if (!loadingMore) return null;
        return (
            <View style={styles.footerLoader}>
                <ActivityIndicator size="small" color={COLORS.accent} />
            </View>
        );
    };

    const renderEmpty = () => (
        <View style={styles.emptyState}>
            <Ionicons
                name={isPast ? "archive-outline" : "musical-notes-outline"}
                size={48}
                color={COLORS.textMuted}
            />
            <Text style={styles.emptyTitle}>
                {isPast ? "No past events" : "No upcoming events"}
            </Text>
            <Text style={styles.emptySubtitle}>
                {isPast
                    ? "Completed events will appear here."
                    : "Accepted engagements will show up once they're confirmed."}
            </Text>
        </View>
    );

    // -----------------------------------------------------------------------
    // Main render
    // -----------------------------------------------------------------------

    // Tab indicator slides left/right
    const indicatorTranslate = tabAnim.interpolate({
        inputRange: [0, 1],
        outputRange: [0, 1], // we'll use flex layout instead
    });

    return (
        <SafeAreaView style={styles.safeArea}>
            {/* Header */}
            <View style={styles.header}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.backButton}
                >
                    <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
                </TouchableOpacity>
                <View style={{ flex: 1 }}>
                    <Text style={styles.headerTitle}>Live Events</Text>
                    <Text style={styles.headerSubtitle}>
                        {scope === "upcoming"
                            ? `${upcomingCount} upcoming`
                            : `${pastCount} past`}{" "}
                        accepted engagements
                    </Text>
                </View>
            </View>

            {/* Scope tab bar */}
            <View style={styles.tabBar}>
                <TouchableOpacity
                    onPress={() => switchTab("upcoming")}
                    style={[
                        styles.tab,
                        scope === "upcoming" && styles.tabActive,
                    ]}
                    activeOpacity={0.8}
                >
                    <Ionicons
                        name="flash"
                        size={14}
                        color={scope === "upcoming" ? COLORS.textPrimary : COLORS.textMuted}
                    />
                    <Text
                        style={[
                            styles.tabText,
                            scope === "upcoming" && styles.tabTextActive,
                        ]}
                    >
                        Upcoming
                    </Text>
                    {upcomingCount > 0 && (
                        <View style={[
                            styles.countBadge,
                            scope === "upcoming"
                                ? { backgroundColor: COLORS.liveGreen }
                                : { backgroundColor: COLORS.tabInactive },
                        ]}>
                            <Text style={styles.countBadgeText}>{upcomingCount}</Text>
                        </View>
                    )}
                </TouchableOpacity>

                <TouchableOpacity
                    onPress={() => switchTab("past")}
                    style={[
                        styles.tab,
                        scope === "past" && styles.tabActive,
                    ]}
                    activeOpacity={0.8}
                >
                    <Ionicons
                        name="archive-outline"
                        size={14}
                        color={scope === "past" ? COLORS.textPrimary : COLORS.textMuted}
                    />
                    <Text
                        style={[
                            styles.tabText,
                            scope === "past" && styles.tabTextActive,
                        ]}
                    >
                        Past
                    </Text>
                    {pastCount > 0 && (
                        <View style={[
                            styles.countBadge,
                            scope === "past"
                                ? { backgroundColor: COLORS.pastGrey }
                                : { backgroundColor: COLORS.tabInactive },
                        ]}>
                            <Text style={styles.countBadgeText}>{pastCount}</Text>
                        </View>
                    )}
                </TouchableOpacity>
            </View>

            {/* Main list */}
            {loading ? (
                <View style={styles.centeredLoader}>
                    <ActivityIndicator size="large" color={COLORS.accent} />
                    <Text style={styles.loadingText}>Loading events…</Text>
                </View>
            ) : (
                <FlatList
                    data={data}
                    keyExtractor={(item) => String(item.id)}
                    renderItem={renderItem}
                    contentContainerStyle={styles.listContent}
                    showsVerticalScrollIndicator={false}
                    ListEmptyComponent={renderEmpty}
                    ListFooterComponent={renderFooter}
                    onEndReached={handleLoadMore}
                    onEndReachedThreshold={0.4}
                    refreshControl={
                        <RefreshControl
                            refreshing={refreshing}
                            onRefresh={handleRefresh}
                            tintColor={COLORS.accent}
                            colors={[COLORS.accent]}
                            progressBackgroundColor={COLORS.card}
                        />
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
        paddingBottom: 8,
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

    // --- Tab bar ---
    tabBar: {
        flexDirection: "row",
        marginHorizontal: 16,
        marginBottom: 8,
        backgroundColor: COLORS.card,
        borderRadius: 12,
        padding: 3,
    },
    tab: {
        flex: 1,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        paddingVertical: 10,
        borderRadius: 10,
    },
    tabActive: {
        backgroundColor: COLORS.tabActive,
    },
    tabText: {
        fontSize: 14,
        fontWeight: "500",
        color: COLORS.textMuted,
    },
    tabTextActive: {
        color: COLORS.textPrimary,
        fontWeight: "600",
    },
    countBadge: {
        paddingHorizontal: 7,
        paddingVertical: 1,
        borderRadius: 999,
        marginLeft: 2,
    },
    countBadgeText: {
        fontSize: 11,
        fontWeight: "700",
        color: COLORS.textPrimary,
    },

    // --- List ---
    listContent: {
        paddingHorizontal: 16,
        paddingBottom: 24,
        paddingTop: 4,
    },

    // --- Card ---
    card: {
        borderRadius: 14,
        padding: 14,
        marginBottom: 12,
        borderWidth: 1,
        borderColor: COLORS.divider,
    },
    cardTopRow: {
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 8,
    },
    dateBlock: {
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
    },
    dateText: {
        fontSize: 16,
        fontWeight: "700",
    },
    timeBlock: {
        flexDirection: "row",
        alignItems: "center",
        gap: 4,
    },
    timeText: {
        fontSize: 14,
        fontWeight: "500",
    },
    occasion: {
        fontSize: 17,
        fontWeight: "600",
        marginBottom: 6,
    },
    detailRow: {
        flexDirection: "row",
        alignItems: "center",
        gap: 5,
        marginBottom: 8,
    },
    detailText: {
        fontSize: 13,
        flex: 1,
    },
    peopleRow: {
        flexDirection: "row",
        gap: 12,
    },
    personChip: {
        flexDirection: "row",
        alignItems: "center",
        gap: 4,
        backgroundColor: "rgba(255,255,255,0.05)",
        paddingHorizontal: 10,
        paddingVertical: 5,
        borderRadius: 999,
    },
    personText: {
        fontSize: 12,
        fontWeight: "500",
    },
    statusPill: {
        alignSelf: "flex-start",
        marginTop: 8,
        paddingHorizontal: 10,
        paddingVertical: 3,
        borderRadius: 999,
    },
    statusPillText: {
        fontSize: 11,
        fontWeight: "600",
        color: COLORS.textSecondary,
    },

    // --- Loaders & empty ---
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
        marginTop: 60,
        alignItems: "center",
        paddingHorizontal: 32,
    },
    emptyTitle: {
        fontSize: 18,
        fontWeight: "600",
        color: COLORS.textPrimary,
        marginTop: 12,
    },
    emptySubtitle: {
        fontSize: 14,
        color: COLORS.textMuted,
        textAlign: "center",
        marginTop: 6,
        lineHeight: 20,
    },
});
