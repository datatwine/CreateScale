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
    SafeAreaView,
    ScrollView,
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
// Color palette — consistent with ProfileScreen + GlobalFeedScreen
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
    badgeGreen: "#1B5E20",
    badgeGreenText: "#A5D6A7",
    badgeAmber: "#5D4037",
    badgeAmberText: "#FFE0B2",
    danger: "#B71C1C",
    dangerText: "#FFCDD2",
};

// ---------------------------------------------------------------------------
// UploadCard — reusable read-only card (same layout as ProfileScreen)
// ---------------------------------------------------------------------------

function UploadCard({ upload }) {
    const imageUrl = makeMediaUrl(upload.image_url);
    const videoUrl = makeMediaUrl(upload.video_url);
    const caption = upload.caption || "";

    return (
        <View style={styles.uploadCard}>
            {/* Image preview */}
            {imageUrl ? (
                <Image
                    source={{ uri: imageUrl }}
                    style={styles.uploadImage}
                    resizeMode="cover"
                />
            ) : videoUrl ? (
                // Video placeholder — future: use expo-av <Video>
                <View style={styles.uploadFallback}>
                    <Ionicons name="videocam" size={32} color={COLORS.textMuted} />
                    <Text style={styles.uploadFallbackText}>Video upload</Text>
                </View>
            ) : (
                <View style={styles.uploadFallback}>
                    <Text style={styles.uploadFallbackText}>No preview</Text>
                </View>
            )}

            {/* Caption */}
            {caption ? (
                <Text style={styles.uploadCaption} numberOfLines={2}>
                    {caption}
                </Text>
            ) : null}

            {/* Date */}
            {upload.upload_date ? (
                <Text style={styles.uploadDate}>
                    {new Date(upload.upload_date).toLocaleDateString()}
                </Text>
            ) : null}
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
                <Ionicons name="ban" size={18} color={COLORS.dangerText} />
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
                <Ionicons name="information-circle" size={18} color={COLORS.badgeAmberText} />
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
                <Ionicons name="time" size={18} color={COLORS.badgeAmberText} />
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
            <TouchableOpacity
                style={styles.hireButton}
                onPress={() => setShowForm(true)}
            >
                <Ionicons name="briefcase" size={18} color={COLORS.textPrimary} />
                <Text style={styles.hireButtonText}>
                    Hire {targetProfile.username}
                </Text>
            </TouchableOpacity>
        );
    }

    // Inline hire form (mirrors hire_form.html fields)
    return (
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
            <SafeAreaView style={styles.safeArea}>
                <View style={styles.centeredLoader}>
                    <ActivityIndicator size="large" color={COLORS.accent} />
                    <Text style={styles.loadingText}>Loading profile…</Text>
                </View>
            </SafeAreaView>
        );
    }

    const avatarUrl = makeMediaUrl(profile.profile_picture_url);
    const uploads = profile.uploads || [];

    return (
        <SafeAreaView style={styles.safeArea}>
            <ScrollView contentContainerStyle={styles.scrollContent}>
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
                        uploads.map((u) => <UploadCard key={u.id} upload={u} />)
                    ) : (
                        <Text style={styles.emptyText}>No uploads yet.</Text>
                    )}
                </View>
            </ScrollView>
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
        paddingBottom: 32,
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
        padding: 20,
        alignItems: "center",
        marginBottom: 16,
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
        backgroundColor: "#1A2040",
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
        backgroundColor: COLORS.badgeGreen,
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 999,
        marginTop: 10,
    },
    performerBadgeText: {
        fontSize: 12,
        fontWeight: "600",
        color: COLORS.badgeGreenText,
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
        backgroundColor: COLORS.accent,
        borderRadius: 999,
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
        backgroundColor: COLORS.card,
        borderRadius: 16,
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
        backgroundColor: COLORS.inputBg,
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

    // --- Upload cards (same as ProfileScreen) ---
    uploadCard: {
        width: "100%",
        padding: 10,
        marginBottom: 16,
        borderRadius: 14,
        backgroundColor: COLORS.card,
        borderWidth: 1,
        borderColor: COLORS.divider,
    },
    uploadImage: {
        width: "100%",
        aspectRatio: 3 / 4,
        borderRadius: 12,
        marginBottom: 8,
    },
    uploadFallback: {
        width: "100%",
        height: 140,
        borderRadius: 12,
        marginBottom: 8,
        backgroundColor: "#1A2040",
        alignItems: "center",
        justifyContent: "center",
    },
    uploadFallbackText: {
        color: COLORS.textMuted,
        fontSize: 13,
        marginTop: 4,
    },
    uploadCaption: {
        color: COLORS.textPrimary,
        fontSize: 13,
        marginTop: 2,
    },
    uploadDate: {
        color: COLORS.textMuted,
        fontSize: 11,
        marginTop: 4,
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
