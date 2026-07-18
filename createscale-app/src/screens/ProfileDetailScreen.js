// src/screens/ProfileDetailScreen.js
//
// Read-only view of another user's profile, shown when tapping a card
// in GlobalFeedScreen.  Mirrors users/templates/users/profile_detail.html.
//
// Features:
//   - Profile picture, username, profession, location, bio
//   - "Available for hire" badge when is_performer
//   - Conditional hire button + inline hire form (date, time, venue, occasion)
//     → POST /api/bookings/hire/<performer_id>/
//   - Uploads gallery (full-width cards, newest first)
//   - Message placeholder (future sprint)
//
// Backend endpoints used:
//   GET  /api/users/profiles/<userId>/       → PublicProfileDetailSerializer
//   GET  /api/users/me/                      → current user's client flags
//   POST /api/bookings/hire/<performer_id>/  → send hire request

import React, {
    useCallback,
    useContext,
    useEffect,
    useState,
} from "react";
import {
    ActivityIndicator,
    Alert,
    Image,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { API_BASE_URL } from "../config/api";
import { AuthContext } from "../context/AuthContext";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";

// ---------------------------------------------------------------------------
// Shared helpers (same as GlobalFeedScreen / ProfileScreen)
// ---------------------------------------------------------------------------

/** Build an absolute URL for API endpoints. */
function buildApiUrl(path) {
    const trimmedBase = API_BASE_URL.replace(/\/+$/, "");
    const trimmedPath = path.replace(/^\/+/, "");
    return `${trimmedBase}/${trimmedPath}`;
}

/**
 * Resolve a relative media path ("/media/...") to an absolute URL.
 * Passthrough for already-absolute URLs.
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
// UploadGridItem — square thumbnail for 3-column grid
// ---------------------------------------------------------------------------

function UploadGridItem({ upload }) {
    const imageUrl = makeMediaUrl(upload.image_url);
    const videoUrl = makeMediaUrl(upload.video_url);

    return (
        <View style={styles.gridItem}>
            <View style={styles.gridItemInner}>
                {imageUrl ? (
                    <Image source={{ uri: imageUrl }} style={styles.gridImage} resizeMode="cover" />
                ) : videoUrl ? (
                    <View style={styles.gridFallback}>
                        <Ionicons name="videocam" size={20} color={COLORS.textMuted} />
                    </View>
                ) : (
                    <View style={styles.gridFallback}>
                        <Ionicons name="image-outline" size={20} color={COLORS.textMuted} />
                    </View>
                )}
            </View>
        </View>
    );
}

// ---------------------------------------------------------------------------
// HireSection — conditional hire button + inline form
// Mirrors profile_detail.html lines 31-46 + hire_form.html
// ---------------------------------------------------------------------------

function HireSection({ targetProfile, myProfile, token, onHireSuccess }) {
    // All hooks MUST be called before any early returns (React Rules of Hooks)
    const [showForm, setShowForm] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    // Hire form fields (matches EngagementCreateSerializer)
    const [date, setDate] = useState("");       // YYYY-MM-DD
    const [time, setTime] = useState("");       // HH:MM
    const [venue, setVenue] = useState("");
    const [occasion, setOccasion] = useState("");

    // --- Gate checks (same logic as profile_detail.html lines 32-45) ---
    // NOTE: these are AFTER hooks so we comply with Rules of Hooks.

    // Target must be a performer
    if (!targetProfile.is_performer) return null;

    // Client blacklisted? (Rule 4)
    if (myProfile?.client_blacklisted) {
        return (
            <View style={styles.hireNotice}>
                <Ionicons name="ban" size={18} color={"#FFCDD2"} />
                <Text style={styles.hireNoticeText}>
                    You are currently blocked from hiring performers.
                </Text>
            </View>
        );
    }

    // Client toggle not enabled? (Rule 2)
    if (!myProfile?.is_potential_client) {
        return (
            <View style={styles.hireNotice}>
                <Ionicons name="information-circle" size={18} color={"#FFE0B2"} />
                <Text style={styles.hireNoticeText}>
                    Enable "I hire performers" on your profile to send hire requests.
                </Text>
            </View>
        );
    }

    // Not admin-approved yet? (Rule 3)
    if (!myProfile?.client_approved) {
        return (
            <View style={styles.hireNotice}>
                <Ionicons name="time" size={18} color={"#FFE0B2"} />
                <Text style={styles.hireNoticeText}>
                    Your account is waiting for admin approval to hire performers.
                </Text>
            </View>
        );
    }

    // --- All checks passed: show hire button / form ---

    const handleSubmitHire = async () => {
        // Basic client-side validation
        if (!date || !time || !venue || !occasion) {
            Alert.alert("Missing fields", "Please fill in all fields.");
            return;
        }

        setSubmitting(true);
        try {
            const res = await fetch(
                buildApiUrl(`/bookings/hire/${targetProfile.user_id}/`),
                {
                    method: "POST",
                    headers: {
                        Authorization: `Token ${token}`,
                        "Content-Type": "application/json",
                        Accept: "application/json",
                    },
                    body: JSON.stringify({ date, time, venue, occasion }),
                },
            );

            if (res.ok) {
                Alert.alert("Success", "Hire request sent!");
                setShowForm(false);
                // Reset form fields
                setDate("");
                setTime("");
                setVenue("");
                setOccasion("");
                onHireSuccess?.();
            } else {
                const data = await res.json().catch(() => ({}));
                Alert.alert(
                    "Could not send request",
                    data.detail || "Please check your inputs and try again.",
                );
            }
        } catch (err) {
            console.error("Hire request failed:", err);
            Alert.alert("Error", "Network error. Please try again.");
        } finally {
            setSubmitting(false);
        }
    };

    if (!showForm) {
        return (
            <PressableStamp
                stampOffset={3} borderRadius={999} borderColor={COLORS.ink} borderWidth={2}
                onPress={() => setShowForm(true)}
                style={styles.hireButton}
            >
                <Ionicons name="briefcase" size={18} color={COLORS.textPrimary} />
                <Text style={styles.hireButtonText}>
                    Hire {targetProfile.username}
                </Text>
            </PressableStamp>
        );
    }

    // Inline hire form (mirrors hire_form.html fields)
    return (
        <PressableStamp stampOffset={4} borderRadius={16} borderColor={COLORS.ink} borderWidth={2}>
        <View style={styles.hireForm}>
            <Text style={styles.hireFormTitle}>
                Hire {targetProfile.username}
            </Text>
            <Text style={styles.hireFormSubtitle}>
                Fill in the details for this engagement.
            </Text>

            {/* Date — YYYY-MM-DD */}
            <Text style={styles.inputLabel}>Date</Text>
            <TextInput
                style={styles.formInput}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={COLORS.textMuted}
                value={date}
                onChangeText={setDate}
                keyboardType={Platform.OS === "ios" ? "default" : "default"}
            />

            {/* Time — HH:MM */}
            <Text style={styles.inputLabel}>Time</Text>
            <TextInput
                style={styles.formInput}
                placeholder="HH:MM (24h)"
                placeholderTextColor={COLORS.textMuted}
                value={time}
                onChangeText={setTime}
            />

            {/* Venue */}
            <Text style={styles.inputLabel}>Venue</Text>
            <TextInput
                style={styles.formInput}
                placeholder="Where is the event?"
                placeholderTextColor={COLORS.textMuted}
                value={venue}
                onChangeText={setVenue}
            />

            {/* Occasion */}
            <Text style={styles.inputLabel}>Occasion</Text>
            <TextInput
                style={styles.formInput}
                placeholder="What's the occasion?"
                placeholderTextColor={COLORS.textMuted}
                value={occasion}
                onChangeText={setOccasion}
            />

            {/* Action buttons */}
            <View style={styles.hireFormActions}>
                <TouchableOpacity
                    style={styles.hireSendButton}
                    onPress={handleSubmitHire}
                    disabled={submitting}
                >
                    <Text style={styles.hireSendButtonText}>
                        {submitting ? "Sending…" : "Send hire request"}
                    </Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={styles.hireCancelButton}
                    onPress={() => setShowForm(false)}
                >
                    <Text style={styles.hireCancelButtonText}>Cancel</Text>
                </TouchableOpacity>
            </View>
        </View>
        </PressableStamp>
    );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function ProfileDetailScreen({ route, navigation }) {
    const { token } = useContext(AuthContext);
    const { userId } = route.params;

    // Target user's profile data (from PublicProfileDetailSerializer)
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);

    // Current user's profile (for hire-button gating)
    const [myProfile, setMyProfile] = useState(null);

    // --- Fetch the target user's profile ---
    const fetchProfile = useCallback(async () => {
        if (!token || !userId) return;
        try {
            const res = await fetch(
                buildApiUrl(`/users/profiles/${userId}/`),
                {
                    headers: {
                        Authorization: `Token ${token}`,
                        Accept: "application/json",
                    },
                },
            );
            if (!res.ok) {
                Alert.alert("Error", "Could not load this profile.");
                return;
            }
            const data = await res.json();
            setProfile(data);
        } catch (err) {
            console.error("Profile fetch failed:", err);
            Alert.alert("Error", "Network error loading profile.");
        }
    }, [token, userId]);

    // --- Fetch current user's own profile (for client flags) ---
    const fetchMyProfile = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(buildApiUrl("/users/me/"), {
                headers: {
                    Authorization: `Token ${token}`,
                    Accept: "application/json",
                },
            });
            if (res.ok) {
                setMyProfile(await res.json());
            }
        } catch (err) {
            console.warn("Failed to load own profile for hire checks:", err);
        }
    }, [token]);

    useEffect(() => {
        const load = async () => {
            setLoading(true);
            await Promise.all([fetchProfile(), fetchMyProfile()]);
            setLoading(false);
        };
        load();
    }, [fetchProfile, fetchMyProfile]);

    // --- Loading state ---
    if (loading || !profile) {
        return (
            <SafeAreaView style={styles.safeArea} edges={["top"]}>
                <View style={styles.centeredLoader}>
                    <ActivityIndicator size="large" color={COLORS.accent} />
                    <Text style={styles.loadingText}>Loading profile…</Text>
                </View>
            </SafeAreaView>
        );
    }

    const avatarUrl = makeMediaUrl(profile.profile_picture_url);
    const coverUrl = profile.cover_photo_url ? makeMediaUrl(profile.cover_photo_url) : null;
    const uploads = profile.uploads || [];

    return (
        <SafeAreaView style={styles.safeArea} edges={["top"]}>
            <View style={{ flex: 1, backgroundColor: COLORS.background }}>
            <ScrollView bounces={false} showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
                {/* Header with back button */}
                <View style={styles.header}>
                    <TouchableOpacity
                        onPress={() => navigation.goBack()}
                        style={styles.backButton}
                    >
                        <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle} numberOfLines={1}>
                        {profile.username}'s Profile
                    </Text>
                </View>

                {/* Profile card */}
                <View style={styles.profileCard}>
                    {/* Cover photo banner — cover_photo if set, else profile_picture */}
                    {coverUrl ? (
                        <Image
                            source={{ uri: coverUrl }}
                            style={styles.coverBanner}
                            resizeMode="cover"
                        />
                    ) : null}

                    {/* Card body — padded content below the cover banner */}
                    <View style={styles.profileCardBody}>
                        {/* Avatar */}
                        <View style={styles.avatarContainer}>
                            {avatarUrl ? (
                                <Image source={{ uri: avatarUrl }} style={styles.avatar} />
                            ) : (
                                <View style={[styles.avatar, styles.avatarPlaceholder]}>
                                    <Text style={styles.avatarInitial}>
                                        {(profile.username || "?").charAt(0).toUpperCase()}
                                    </Text>
                                </View>
                            )}
                        </View>

                        {/* Name + profession */}
                        <Text style={styles.profileName}>{profile.username}</Text>

                        {profile.profession ? (
                            <Text style={styles.profileProfession}>
                                {profile.profession}
                            </Text>
                        ) : null}

                        {/* Performer badge */}
                        {profile.is_performer && (
                            <View style={styles.performerBadge}>
                                <Ionicons name="star" size={14} color={COLORS.badgeGreenText} />
                                <Text style={styles.performerBadgeText}>
                                    Available for hire
                                </Text>
                            </View>
                        )}

                        {/* Location */}
                        {profile.location ? (
                            <View style={styles.infoRow}>
                                <Ionicons name="location" size={16} color={COLORS.textMuted} />
                                <Text style={styles.infoText}>{profile.location}</Text>
                            </View>
                        ) : null}

                        {/* Bio */}
                        {profile.bio ? (
                            <View style={styles.bioSection}>
                                <Text style={styles.sectionLabel}>BIO</Text>
                                <Text style={styles.bioText}>{profile.bio}</Text>
                            </View>
                        ) : null}
                    </View>
                </View>

                {/* Hire section — conditional, mirrors profile_detail.html */}
                <View style={styles.sectionBlock}>
                    <HireSection
                        targetProfile={profile}
                        myProfile={myProfile}
                        token={token}
                        onHireSuccess={fetchProfile}
                    />
                </View>

                {/* Message placeholder — future sprint */}
                <TouchableOpacity
                    style={styles.messageButton}
                    onPress={() =>
                        Alert.alert(
                            "Coming soon",
                            "In-app messaging will be available in a future update.",
                        )
                    }
                >
                    <Ionicons name="chatbubble-outline" size={18} color={COLORS.accent} />
                    <Text style={styles.messageButtonText}>
                        Message {profile.username}
                    </Text>
                </TouchableOpacity>

                {/* Uploads gallery */}
                <View style={styles.sectionBlock}>
                    <Text style={styles.sectionTitle}>Uploads</Text>
                    {uploads.length > 0 ? (
                        <View style={styles.gridContainer}>
                            {uploads.map((u) => (
                                <UploadGridItem key={u.id} upload={u} />
                            ))}
                        </View>
                    ) : (
                        <Text style={styles.emptyText}>No uploads yet.</Text>
                    )}
                </View>
            </ScrollView>
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
        backgroundColor: COLORS.background,
    },
    scrollContent: {
        paddingHorizontal: 16,
    },

    // --- Header ---
    header: {
        flexDirection: "row",
        alignItems: "center",
        paddingTop: 8,
        paddingBottom: 12,
    },
    backButton: {
        marginRight: 12,
        padding: 4,
    },
    headerTitle: {
        fontSize: 22,
        fontWeight: "700",
        color: COLORS.textPrimary,
        flexShrink: 1,
    },

    // --- Profile card ---
    profileCard: {
        backgroundColor: COLORS.card,
        borderRadius: 20,
        borderWidth: 2,
        borderColor: COLORS.ink,
        padding: 20,
        alignItems: "center",
        marginBottom: 16,
    },
    coverBanner: {
        width: "100%",
        height: 140,
    },
    profileCardBody: {
        padding: 20,
        alignItems: "center",
    },
    avatarContainer: {
        marginBottom: 12,
    },
    avatar: {
        width: 96,
        height: 96,
        borderRadius: 48,
        borderWidth: 3,
        borderColor: COLORS.accent,
    },
    avatarPlaceholder: {
        backgroundColor: COLORS.cream,
        alignItems: "center",
        justifyContent: "center",
    },
    avatarInitial: {
        fontSize: 36,
        fontWeight: "700",
        color: COLORS.accent,
    },
    profileName: {
        fontSize: 22,
        fontWeight: "700",
        color: COLORS.textPrimary,
    },
    profileProfession: {
        fontSize: 15,
        color: COLORS.accent,
        marginTop: 2,
    },
    performerBadge: {
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        backgroundColor: "#1B5E20",
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 999,
        marginTop: 10,
    },
    performerBadgeText: {
        fontSize: 12,
        fontWeight: "600",
        color: "#A5D6A7",
    },
    infoRow: {
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        marginTop: 10,
    },
    infoText: {
        fontSize: 14,
        color: COLORS.textSecondary,
    },
    bioSection: {
        marginTop: 14,
        width: "100%",
    },
    sectionLabel: {
        fontSize: 12,
        fontWeight: "600",
        color: COLORS.textMuted,
        letterSpacing: 1,
        marginBottom: 4,
    },
    bioText: {
        fontSize: 14,
        color: COLORS.textSecondary,
        lineHeight: 20,
    },

    // --- Hire section ---
    hireNotice: {
        flexDirection: "row",
        alignItems: "center",
        gap: 8,
        backgroundColor: COLORS.card,
        borderRadius: 12,
        borderWidth: 1.5,
        borderColor: COLORS.accent,
        borderStyle: "dashed",
        padding: 14,
        marginBottom: 12,
    },
    hireNoticeText: {
        fontSize: 13,
        color: COLORS.textMuted,
        flexShrink: 1,
    },
    hireButton: {
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        paddingVertical: 12,
        paddingHorizontal: 20,
        marginBottom: 12,
    },
    hireButtonText: {
        fontSize: 15,
        fontWeight: "600",
        color: COLORS.textPrimary,
    },

    // --- Hire form ---
    hireForm: {
        padding: 16,
        marginBottom: 12,
    },
    hireFormTitle: {
        fontSize: 18,
        fontWeight: "700",
        color: COLORS.textPrimary,
        marginBottom: 4,
    },
    hireFormSubtitle: {
        fontSize: 13,
        color: COLORS.textMuted,
        marginBottom: 14,
    },
    inputLabel: {
        fontSize: 12,
        fontWeight: "600",
        color: COLORS.textSecondary,
        marginBottom: 4,
        marginTop: 10,
    },
    formInput: {
        backgroundColor: COLORS.cream,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: COLORS.divider,
        paddingHorizontal: 12,
        paddingVertical: 10,
        color: COLORS.textPrimary,
        fontSize: 14,
    },
    hireFormActions: {
        flexDirection: "row",
        gap: 10,
        marginTop: 16,
    },
    hireSendButton: {
        flex: 1,
        backgroundColor: COLORS.accent,
        borderRadius: 999,
        paddingVertical: 11,
        alignItems: "center",
    },
    hireSendButtonText: {
        color: COLORS.textPrimary,
        fontWeight: "600",
        fontSize: 14,
    },
    hireCancelButton: {
        flex: 1,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: COLORS.divider,
        paddingVertical: 11,
        alignItems: "center",
    },
    hireCancelButtonText: {
        color: COLORS.textSecondary,
        fontSize: 14,
    },

    // --- Message button ---
    messageButton: {
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: COLORS.accent,
        paddingVertical: 11,
        marginBottom: 20,
    },
    messageButtonText: {
        color: COLORS.accent,
        fontSize: 14,
        fontWeight: "500",
    },

    // --- Section blocks ---
    sectionBlock: {
        marginBottom: 8,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: "700",
        color: COLORS.textPrimary,
        marginBottom: 12,
    },

    // --- Upload grid ---
    gridContainer: {
        flexDirection: "row",
        flexWrap: "wrap",
    },
    gridItem: {
        width: "33.333%",
        aspectRatio: 1,
        padding: 2,
    },
    gridItemInner: {
        flex: 1,
        borderRadius: 6,
        backgroundColor: COLORS.card,
        borderWidth: 1.5,
        borderColor: COLORS.ink,
        overflow: "hidden",
    },
    gridImage: {
        width: "100%",
        height: "100%",
    },
    gridFallback: {
        flex: 1,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: COLORS.cream,
    },

    // --- Loaders ---
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
    emptyText: {
        color: COLORS.textMuted,
        fontSize: 14,
        textAlign: "center",
        marginTop: 8,
    },
});
