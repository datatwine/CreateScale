// src/screens/BookingsScreen.js
//
// Unified engagement dashboard — shows all bookings where the logged-in
// user is either the client (hirer) or performer.
//
// Mirrors:
//   bookings/templates/bookings/client_engagements.html
//   bookings/templates/bookings/performer_engagements.html
//   bookings/templates/bookings/engagement_detail.html
//
// Backend endpoints used (zero changes required):
//   GET  /api/bookings/engagements/            → all engagements for user
//   POST /api/bookings/engagements/<pk>/action/ → accept/decline/cancel
//
// Engagement statuses (from Engagement model):
//   pending | accepted | declined | cancelled_client | cancelled_performer | auto_expired
//
// Business rules enforced server-side:
//   - Performer accept/decline only on pending (Rule 9: 24h window)
//   - Cancel within 24h requires emergency_reason (Rules 10, 11)
//   - Only 1 accepted booking per performer per date (Rule 7)

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
    SafeAreaView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a full API URL from a relative path. */
function buildApiUrl(path) {
    const base = API_BASE_URL.replace(/\/+$/, "");
    const rel = path.replace(/^\/+/, "");
    return `${base}/${rel}`;
}

// ---------------------------------------------------------------------------
// Color palette — consistent with the rest of the app
// ---------------------------------------------------------------------------

const COLORS = {
    background: "#0B0F1A",
    card: "#141A2E",
    accent: "#E68A00",
    textPrimary: "#FFFFFF",
    textSecondary: "#CFCFCF",
    textMuted: "#8A8FA0",
    divider: "#2B2B2B",
    inputBg: "#181818",
    // Status badge colors
    statusPending: "#E68A00",       // amber
    statusAccepted: "#2E7D32",      // green
    statusDeclined: "#B71C1C",      // red
    statusCancelled: "#6D4C41",     // brown-ish
    statusExpired: "#424242",       // grey
    // Action button colors
    acceptGreen: "#388E3C",
    declineRed: "#C62828",
    cancelOrange: "#E65100",
};

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

/** Human-readable label for each status (mirrors get_status_display). */
const STATUS_LABELS = {
    pending: "Pending",
    accepted: "Accepted",
    declined: "Declined",
    cancelled_client: "Cancelled by client",
    cancelled_performer: "Cancelled by performer",
    auto_expired: "Auto expired",
};

/** Background color for the status badge. */
const STATUS_COLORS = {
    pending: COLORS.statusPending,
    accepted: COLORS.statusAccepted,
    declined: COLORS.statusDeclined,
    cancelled_client: COLORS.statusCancelled,
    cancelled_performer: COLORS.statusCancelled,
    auto_expired: COLORS.statusExpired,
};

/** Is this status still "active" (i.e. can have actions)? */
function isActive(status) {
    return status === "pending" || status === "accepted";
}

// ---------------------------------------------------------------------------
// EngagementCard — a single booking row with expandable actions
// ---------------------------------------------------------------------------

function EngagementCard({ engagement, myUserId, token, onActionDone }) {
    const [expanded, setExpanded] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [emergencyReason, setEmergencyReason] = useState("");

    // Determine current user's role in this engagement
    const isClient = engagement.client.id === myUserId;
    const isPerformer = engagement.performer.id === myUserId;

    // The "other party" — show performer name if I'm client, client name if I'm performer
    const otherName = isClient
        ? engagement.performer.username
        : engagement.client.username;
    const roleLabel = isClient ? "You hired" : "Hired by";

    const statusLabel = STATUS_LABELS[engagement.status] || engagement.status;
    const statusColor = STATUS_COLORS[engagement.status] || COLORS.textMuted;

    // Format date nicely
    const dateStr = engagement.date; // "YYYY-MM-DD" from DRF
    const timeStr = engagement.time; // "HH:MM:SS" from DRF

    // --- Determine which actions are available ---
    // Mirrors engagement_detail.html conditional logic exactly:
    //   Performer + pending → accept, decline
    //   Performer + (pending|accepted) → cancel_performer
    //   Client + (pending|accepted) → cancel_client
    const canAccept = isPerformer && engagement.status === "pending";
    const canDecline = isPerformer && engagement.status === "pending";
    const canCancelPerformer = isPerformer && isActive(engagement.status);
    const canCancelClient = isClient && isActive(engagement.status);
    const hasActions = canAccept || canDecline || canCancelPerformer || canCancelClient;

    // --- Action handler ---
    // Posts to /api/bookings/engagements/<pk>/action/
    // Body: { action: "accept"|"decline"|"cancel_client"|"cancel_performer", emergency_reason: "..." }
    const performAction = async (actionName) => {
        setActionLoading(true);
        try {
            const body = { action: actionName };

            // Include emergency reason for cancel actions (server enforces 24h rule)
            if (actionName === "cancel_client" || actionName === "cancel_performer") {
                body.emergency_reason = emergencyReason;
            }

            const res = await fetch(
                buildApiUrl(`/bookings/engagements/${engagement.id}/action/`),
                {
                    method: "POST",
                    headers: {
                        Authorization: `Token ${token}`,
                        "Content-Type": "application/json",
                        Accept: "application/json",
                    },
                    body: JSON.stringify(body),
                },
            );

            const data = await res.json().catch(() => ({}));

            if (res.ok) {
                Alert.alert("Done", data.detail || "Action completed.");
                setEmergencyReason("");
                setExpanded(false);
                onActionDone(); // re-fetch list
            } else {
                // Server returns { detail: "..." } for validation errors
                Alert.alert("Error", data.detail || "Something went wrong.");
            }
        } catch (err) {
            console.error("Engagement action failed:", err);
            Alert.alert("Error", "Network error. Please try again.");
        } finally {
            setActionLoading(false);
        }
    };

    // --- Confirm destructive actions ---
    const confirmAction = (actionName, label) => {
        Alert.alert(
            `${label}?`,
            `Are you sure you want to ${label.toLowerCase()} this booking?`,
            [
                { text: "No", style: "cancel" },
                { text: "Yes", onPress: () => performAction(actionName) },
            ],
        );
    };

    return (
        <TouchableOpacity
            style={styles.card}
            activeOpacity={0.85}
            onPress={() => setExpanded(!expanded)}
        >
            {/* Top row: role label + other party + status badge */}
            <View style={styles.cardTopRow}>
                <View style={styles.cardInfo}>
                    <Text style={styles.roleLabel}>{roleLabel}</Text>
                    <Text style={styles.otherName} numberOfLines={1}>
                        {otherName}
                    </Text>
                </View>
                <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
                    <Text style={styles.statusBadgeText}>{statusLabel}</Text>
                </View>
            </View>

            {/* Date / time / venue row */}
            <View style={styles.detailRow}>
                <View style={styles.detailItem}>
                    <Ionicons name="calendar-outline" size={14} color={COLORS.textMuted} />
                    <Text style={styles.detailText}>{dateStr}</Text>
                </View>
                <View style={styles.detailItem}>
                    <Ionicons name="time-outline" size={14} color={COLORS.textMuted} />
                    <Text style={styles.detailText}>{timeStr}</Text>
                </View>
            </View>
            <View style={styles.detailRow}>
                <View style={styles.detailItem}>
                    <Ionicons name="location-outline" size={14} color={COLORS.textMuted} />
                    <Text style={styles.detailText} numberOfLines={1}>{engagement.venue}</Text>
                </View>
                <View style={styles.detailItem}>
                    <Ionicons name="musical-notes-outline" size={14} color={COLORS.textMuted} />
                    <Text style={styles.detailText} numberOfLines={1}>{engagement.occasion}</Text>
                </View>
            </View>

            {/* Expanded section — full details + action buttons */}
            {expanded && (
                <View style={styles.expandedSection}>
                    {/* Divider */}
                    <View style={styles.expandDivider} />

                    {/* Full party info */}
                    <Text style={styles.expandLabel}>
                        Client: <Text style={styles.expandValue}>{engagement.client.username}</Text>
                    </Text>
                    <Text style={styles.expandLabel}>
                        Performer: <Text style={styles.expandValue}>{engagement.performer.username}</Text>
                    </Text>
                    <Text style={styles.expandLabel}>
                        Created: <Text style={styles.expandValue}>
                            {new Date(engagement.created_at).toLocaleString()}
                        </Text>
                    </Text>

                    {/* Emergency reasons (if any exist) */}
                    {engagement.client_emergency_reason ? (
                        <Text style={styles.emergencyNote}>
                            Client emergency: {engagement.client_emergency_reason}
                        </Text>
                    ) : null}
                    {engagement.performer_emergency_reason ? (
                        <Text style={styles.emergencyNote}>
                            Performer emergency: {engagement.performer_emergency_reason}
                        </Text>
                    ) : null}

                    {/* Action buttons — only shown for active engagements */}
                    {hasActions && !actionLoading && (
                        <View style={styles.actionsBlock}>
                            {/* Performer: Accept + Decline (only when pending) */}
                            {canAccept && (
                                <TouchableOpacity
                                    style={[styles.actionBtn, { backgroundColor: COLORS.acceptGreen }]}
                                    onPress={() => confirmAction("accept", "Accept")}
                                >
                                    <Ionicons name="checkmark-circle" size={16} color="#fff" />
                                    <Text style={styles.actionBtnText}>Accept</Text>
                                </TouchableOpacity>
                            )}
                            {canDecline && (
                                <TouchableOpacity
                                    style={[styles.actionBtn, { backgroundColor: COLORS.declineRed }]}
                                    onPress={() => confirmAction("decline", "Decline")}
                                >
                                    <Ionicons name="close-circle" size={16} color="#fff" />
                                    <Text style={styles.actionBtnText}>Decline</Text>
                                </TouchableOpacity>
                            )}

                            {/* Cancel section — shows for both roles on active bookings */}
                            {(canCancelClient || canCancelPerformer) && (
                                <View style={styles.cancelSection}>
                                    {/* Emergency reason input — server enforces the
                                        24h rule; we always show the field so users
                                        can provide context */}
                                    <Text style={styles.cancelHint}>
                                        Cancelling within 24 hours of the event requires an emergency reason.
                                    </Text>
                                    <TextInput
                                        style={styles.emergencyInput}
                                        placeholder="Emergency reason (if applicable)"
                                        placeholderTextColor={COLORS.textMuted}
                                        value={emergencyReason}
                                        onChangeText={setEmergencyReason}
                                        multiline
                                    />
                                    <TouchableOpacity
                                        style={[styles.actionBtn, { backgroundColor: COLORS.cancelOrange }]}
                                        onPress={() =>
                                            confirmAction(
                                                canCancelClient ? "cancel_client" : "cancel_performer",
                                                "Cancel",
                                            )
                                        }
                                    >
                                        <Ionicons name="ban" size={16} color="#fff" />
                                        <Text style={styles.actionBtnText}>
                                            Cancel as {canCancelClient ? "client" : "performer"}
                                        </Text>
                                    </TouchableOpacity>
                                </View>
                            )}
                        </View>
                    )}

                    {/* Loading spinner while action is in progress */}
                    {actionLoading && (
                        <ActivityIndicator
                            size="small"
                            color={COLORS.accent}
                            style={{ marginTop: 12 }}
                        />
                    )}

                    {/* Terminal state — no actions available */}
                    {!hasActions && (
                        <Text style={styles.terminalNote}>
                            This booking is {statusLabel.toLowerCase()} — no further actions.
                        </Text>
                    )}
                </View>
            )}

            {/* Expand hint */}
            <View style={styles.expandHint}>
                <Ionicons
                    name={expanded ? "chevron-up" : "chevron-down"}
                    size={16}
                    color={COLORS.textMuted}
                />
            </View>
        </TouchableOpacity>
    );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function BookingsScreen({ navigation }) {
    const { token, user } = useContext(AuthContext);

    // AuthContext's user object comes from /api/auth/me/ which returns
    // { user_id, username, profile: {...} } — note: field is "user_id" not "id"
    const myUserId = user?.user_id ?? user?.id;

    const [engagements, setEngagements] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    // --- Fetch all engagements (union of client + performer) ---
    const fetchEngagements = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(buildApiUrl("/bookings/engagements/"), {
                headers: {
                    Authorization: `Token ${token}`,
                    Accept: "application/json",
                },
            });
            if (!res.ok) {
                const text = await res.text();
                console.warn("Bookings fetch failed:", res.status, text);
                return;
            }
            const data = await res.json();
            setEngagements(data);
        } catch (err) {
            console.error("Error loading bookings:", err);
            Alert.alert("Error", "Couldn't load bookings. Please try again.");
        }
    }, [token]);

    // Initial load
    useEffect(() => {
        setLoading(true);
        fetchEngagements().finally(() => setLoading(false));
    }, [fetchEngagements]);

    // Pull-to-refresh
    const handleRefresh = async () => {
        setRefreshing(true);
        await fetchEngagements();
        setRefreshing(false);
    };

    // After an action (accept/decline/cancel) — re-fetch the list
    const handleActionDone = () => {
        fetchEngagements();
    };

    // --- Render ---

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
                <View>
                    <Text style={styles.headerTitle}>Bookings</Text>
                    <Text style={styles.headerSubtitle}>
                        Your hire requests & engagements
                    </Text>
                </View>
            </View>

            {/* List */}
            {loading ? (
                <View style={styles.centeredLoader}>
                    <ActivityIndicator size="large" color={COLORS.accent} />
                    <Text style={styles.loadingText}>Loading bookings…</Text>
                </View>
            ) : (
                <FlatList
                    data={engagements}
                    keyExtractor={(item) => String(item.id)}
                    renderItem={({ item }) => (
                        <EngagementCard
                            engagement={item}
                            myUserId={myUserId}
                            token={token}
                            onActionDone={handleActionDone}
                        />
                    )}
                    contentContainerStyle={styles.listContent}
                    showsVerticalScrollIndicator={false}
                    refreshing={refreshing}
                    onRefresh={handleRefresh}
                    ListEmptyComponent={
                        <View style={styles.emptyState}>
                            <Ionicons name="calendar-outline" size={48} color={COLORS.textMuted} />
                            <Text style={styles.emptyTitle}>No bookings yet</Text>
                            <Text style={styles.emptySubtitle}>
                                Hire a performer from the Global Feed, or wait for clients to find you!
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

    // --- List ---
    listContent: {
        paddingHorizontal: 16,
        paddingBottom: 24,
    },

    // --- Card ---
    card: {
        backgroundColor: COLORS.card,
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
    cardInfo: {
        flexShrink: 1,
    },
    roleLabel: {
        fontSize: 11,
        fontWeight: "600",
        color: COLORS.textMuted,
        textTransform: "uppercase",
        letterSpacing: 0.5,
    },
    otherName: {
        fontSize: 17,
        fontWeight: "700",
        color: COLORS.textPrimary,
        marginTop: 2,
    },

    // --- Status badge ---
    statusBadge: {
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 999,
    },
    statusBadgeText: {
        fontSize: 11,
        fontWeight: "600",
        color: "#FFFFFF",
    },

    // --- Detail rows (date/time/venue/occasion) ---
    detailRow: {
        flexDirection: "row",
        gap: 16,
        marginTop: 4,
    },
    detailItem: {
        flexDirection: "row",
        alignItems: "center",
        gap: 4,
        flex: 1,
    },
    detailText: {
        fontSize: 13,
        color: COLORS.textSecondary,
    },

    // --- Expanded section ---
    expandedSection: {
        marginTop: 8,
    },
    expandDivider: {
        height: 1,
        backgroundColor: COLORS.divider,
        marginBottom: 10,
    },
    expandLabel: {
        fontSize: 13,
        color: COLORS.textMuted,
        marginBottom: 4,
    },
    expandValue: {
        color: COLORS.textSecondary,
        fontWeight: "500",
    },
    emergencyNote: {
        fontSize: 12,
        color: COLORS.statusDeclined,
        fontStyle: "italic",
        marginTop: 4,
    },

    // --- Actions ---
    actionsBlock: {
        marginTop: 12,
        gap: 8,
    },
    actionBtn: {
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        borderRadius: 999,
        paddingVertical: 10,
        paddingHorizontal: 16,
    },
    actionBtnText: {
        color: "#FFFFFF",
        fontSize: 14,
        fontWeight: "600",
    },

    // --- Cancel section ---
    cancelSection: {
        marginTop: 4,
        gap: 8,
    },
    cancelHint: {
        fontSize: 11,
        color: COLORS.textMuted,
        fontStyle: "italic",
    },
    emergencyInput: {
        backgroundColor: COLORS.inputBg,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: COLORS.divider,
        paddingHorizontal: 12,
        paddingVertical: 10,
        color: COLORS.textPrimary,
        fontSize: 14,
        minHeight: 44,
    },

    // --- Terminal state ---
    terminalNote: {
        fontSize: 12,
        color: COLORS.textMuted,
        fontStyle: "italic",
        marginTop: 8,
    },

    // --- Expand hint chevron ---
    expandHint: {
        alignItems: "center",
        marginTop: 6,
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
