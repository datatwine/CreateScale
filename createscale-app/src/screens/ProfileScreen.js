// src/screens/ProfileScreen.js

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
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { Ionicons } from "@expo/vector-icons"; // only once


import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";

/**
 * Central color palette, kept close to your Django CSS:
 * - black / cream split background
 * - orange accents
 * - dark card for content
 */
const COLORS = {
  background: "#000000",
  backgroundRight: "#FFF1DC", // pale cream
  accent: "#E68A00", // orange
  card: "#111111",
  cardOverlay: "rgba(0,0,0,0.7)",
  textPrimary: "#FFFFFF",
  textSecondary: "#CFCFCF",
  textMuted: "#999999",
  badgeYellow: "#FFBF47",
  badgeYellowText: "#432500",
  badgeGreen: "#34C759",
  badgeGreenText: "#002A10",
  badgeRed: "#FF3B30",
  chipBackground: "#1E1E1E",
  divider: "#2B2B2B",
  buttonDark: "#181818",
};


// Renders either an image thumbnail or a simple "video" chip
// for a single upload row. Uses the DRF fields image_url / video_url
// that you tested with curl.
function renderUploadMedia(upload, styles) {
  const imageUrl = upload.image_url || upload.image;
  const videoUrl = upload.video_url || upload.video;

  // If there is an image URL, show a square image
  if (imageUrl) {
    return (
      <Image
        source={{ uri: imageUrl }}
        style={styles.uploadImage}
        resizeMode="cover"
      />
    );
  }

  // If there is a video URL, show a dark chip with a camera icon
  if (videoUrl) {
    return (
      <View style={styles.uploadVideoPlaceholder}>
        <Ionicons name="videocam" size={20} color="#fff" />
        <Text style={styles.uploadVideoText}>Video upload</Text>
      </View>
    );
  }

  // No media – nothing to preview
  return null;
}



/**
 * Convenience helper: build an absolute URL for API endpoints.
 * Keeps the string handling in one place in case you ever swap domains.
 */
function buildApiUrl(path) {
  // Ensure single slash between base and path
  const trimmedBase = API_BASE_URL.replace(/\/+$/, "");
  const trimmedPath = path.replace(/^\/+/, "");
  return `${trimmedBase}/${trimmedPath}`;
}

/**
 * Small pill-style badge component, reused for all status chips.
 */
function StatusBadge({ label, tone = "default" }) {
  let backgroundColor = COLORS.chipBackground;
  let textColor = COLORS.textSecondary;

  if (tone === "positive") {
    backgroundColor = COLORS.badgeGreen;
    textColor = COLORS.badgeGreenText;
  } else if (tone === "warning") {
    backgroundColor = COLORS.badgeYellow;
    textColor = COLORS.badgeYellowText;
  } else if (tone === "danger") {
    backgroundColor = COLORS.badgeRed;
    textColor = COLORS.textPrimary;
  }

  return (
    <View style={[styles.statusBadge, { backgroundColor }]}>
      <Text style={[styles.statusBadgeText, { color: textColor }]}>
        {label}
      </Text>
    </View>
  );
}

/**
 * Reusable toggle pill that looks like a button:
 * - highlighted when "on"
 * - outlined when "off"
 */
function TogglePill({ active, label, onPress }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[
        styles.togglePill,
        active && styles.togglePillActive,
      ]}
    >
      <Text
        style={[
          styles.togglePillText,
          active && styles.togglePillTextActive,
        ]}
      >
        {label}
      </Text>
    </TouchableOpacity>
  );
}


/**
 * Turn whatever the backend gives us for image / video into a usable, absolute
 * URL for React Native's <Image>. This keeps behaviour stable even if
 * DRF returns relative paths ("/media/...").
 */
const makeMediaUrl = (pathOrUrl) => {
  if (!pathOrUrl) return null;

  // If backend already sent an absolute URL, just use it.
  if (
    pathOrUrl.startsWith("http://") ||
    pathOrUrl.startsWith("https://")
  ) {
    return pathOrUrl;
  }

  // Otherwise treat it as relative to the Django root (strip trailing "/api").
  const backendRoot = API_BASE_URL.replace(/\/api\/?$/, "");

  if (pathOrUrl.startsWith("/")) {
    // "/media/..." -> "http://192.168.1.2/media/..."
    return backendRoot + pathOrUrl;
  }

  // "media/..." -> "http://192.168.1.2/media/..."
  return `${backendRoot}/${pathOrUrl}`;
};



/**
 * One upload tile (image / video). For now we just show:
 * - type (Image / Video)
 * - caption
 * - upload date
 * If you later expose thumbnails from the backend, we can drop them in here.
 */
// Tiny presentational helper so the main component stays readable.
// Now shows a thumbnail for image uploads instead of just text.
function UploadCard({ upload }) {
  // What we display as text under the preview
  console.log("UPLOAD CARD DATA", upload);
  const caption = upload.caption || "";

  // Prefer the explicit *_url fields; fall back to raw file fields.
  const rawImage = upload.image_url || upload.image;
  const rawVideo = upload.video_url || upload.video;

  const imageUri = makeMediaUrl(rawImage);
  const videoUri = makeMediaUrl(rawVideo);

  const hasImage = !!imageUri;
  const hasVideo = !hasImage && !!videoUri; // don't double-render

  return (
    <View style={styles.uploadCard}>
      {/* Media preview */}
      {hasImage ? (
        <Image
          source={{ uri: imageUri }}
          style={styles.uploadImage}
          resizeMode="cover"
        />
      ) : hasVideo ? (
        // For now we just show a nice placeholder. Later you can drop in
        // expo-av's <Video> using this same videoUri.
        <View style={styles.uploadFallback}>
          <Text style={styles.uploadFallbackText}>Video upload</Text>
        </View>
      ) : (
        <View style={styles.uploadFallback}>
          <Text style={styles.uploadFallbackText}>No preview</Text>
        </View>
      )}

      {/* Caption */}
      {caption ? (
        <Text style={styles.uploadCaption} numberOfLines={1}>
          {caption}
        </Text>
      ) : null}

      {/* Date, newest first – this matches the website */}
      {upload.upload_date ? (
        <Text style={styles.uploadMeta}>
          {new Date(upload.upload_date).toLocaleString()}
        </Text>
      ) : null}
    </View>
  );
}





export default function ProfileScreen() {
  const navigation = useNavigation();
  const { token, logout } = useContext(AuthContext);

  // --- Profile data + editing state ----------------------------------------

  const [profile, setProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);

  // Fields the user can edit
  const [bio, setBio] = useState("");
  const [profession, setProfession] = useState("");
  const [location, setLocation] = useState("");
  const [isPerformer, setIsPerformer] = useState(false);
  const [isPotentialClient, setIsPotentialClient] = useState(false);

  // Profile picture upload in progress flag
  const [updatingPicture, setUpdatingPicture] = useState(false);

  // --- Uploads (media gallery) ---------------------------------------------

  const [uploads, setUploads] = useState([]);
  const [loadingUploads, setLoadingUploads] = useState(true);
  const [uploadingMedia, setUploadingMedia] = useState(false);
  const [newUploadCaption, setNewUploadCaption] = useState("");

  // -------------------------------------------------------------------------
  // Data loading helpers
  // -------------------------------------------------------------------------

  // Unified avatar URL:
  // Some serializers expose `profile_picture_url`,
  // others expose the raw ImageField as `profile_picture`.
  // Using both makes the mobile UI resilient to backend tweaks.
  // Wrap through makeMediaUrl so relative paths ("/media/...") resolve.
  const avatarUrl = makeMediaUrl(
    profile?.profile_picture_url || profile?.profile_picture || null
  );

  const loadProfile = useCallback(async () => {
    if (!token) return;

    setLoadingProfile(true);
    try {
      const response = await fetch(buildApiUrl("/users/me/"), {
        method: "GET",
        headers: {
          Authorization: `Token ${token}`,
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        // For debugging JSON parse problems:
        const text = await response.text();
        console.warn("Profile load failed:", response.status, text);
        throw new Error("Failed to load profile");
      }

      const data = await response.json();
      setProfile(data);

      // Initialise form state from API data
      setBio(data.bio || "");
      setProfession(data.profession || "");
      setLocation(data.location || "");
      setIsPerformer(Boolean(data.is_performer));
      setIsPotentialClient(Boolean(data.is_potential_client));
    } catch (err) {
      console.error("Error loading profile", err);
      Alert.alert(
        "Error",
        "We couldn’t load your profile. Please try again."
      );
    } finally {
      setLoadingProfile(false);
    }
  }, [token]);

  const loadUploads = useCallback(async () => {
    if (!token) return;

    setLoadingUploads(true);
    try {
      const response = await fetch(
        buildApiUrl("/users/me/uploads/"),
        {
          method: "GET",
          headers: {
            Authorization: `Token ${token}`,
            Accept: "application/json",
          },
        }
      );

      if (!response.ok) {
        const text = await response.text();
        console.warn("Uploads load failed:", response.status, text);
        throw new Error("Failed to load uploads");
      }

      const data = await response.json();

      console.log(
        "UPLOADS FROM API",
        JSON.stringify(data, null, 2)
      );

      setUploads(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error loading uploads", err);
      Alert.alert(
        "Error",
        "We couldn’t load your uploads. You can still upload new media."
      );
    } finally {
      setLoadingUploads(false);
    }
  }, [token]);

  // Load profile and uploads when the screen mounts / token changes
  useEffect(() => {
    if (!token) return;
    loadProfile();
    loadUploads();
  }, [token, loadProfile, loadUploads]);

  // -------------------------------------------------------------------------
  // Mutations: save profile, profile picture, uploads
  // -------------------------------------------------------------------------

  const handleSaveProfile = async () => {
    if (!token || !profile) return;

    setSavingProfile(true);
    try {
      const payload = {
        bio,
        profession,
        location,
        is_performer: isPerformer,
        is_potential_client: isPotentialClient,
      };

      const response = await fetch(buildApiUrl("/users/me/"), {
        method: "PATCH",
        headers: {
          Authorization: `Token ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text();
        console.warn(
          "Profile update failed:",
          response.status,
          text
        );
        throw new Error("Failed to update profile");
      }

      const updated = await response.json();
      setProfile(updated); // keep UI in sync
      Alert.alert("Saved", "Your profile has been updated.");
    } catch (err) {
      console.error("Error updating profile", err);
      Alert.alert(
        "Error",
        "We couldn’t save your changes. Please try again."
      );
    } finally {
      setSavingProfile(false);
    }
  };

  const handlePickProfilePicture = async () => {
    if (!token) return;

    // Ask for gallery permissions
    const { status } =
      await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Permission needed",
        "We need access to your photos to set a profile picture."
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [1, 1], // force square crop
      quality: 0.8,
    });

    if (result.canceled) return;

    const asset = result.assets && result.assets[0];
    if (!asset) return;

    const formData = new FormData();
    formData.append("profile_picture", {
      uri: asset.uri,
      name: "profile.jpg",
      type: "image/jpeg",
    });

    setUpdatingPicture(true);
    try {
      const response = await fetch(buildApiUrl("/users/me/"), {
        method: "PATCH",
        headers: {
          Authorization: `Token ${token}`,
          // NOTE: do NOT set Content-Type here; fetch will set multipart boundary
          Accept: "application/json",
        },
        body: formData,
      });

      if (!response.ok) {
        const text = await response.text();
        console.warn(
          "Profile picture update failed:",
          response.status,
          text
        );
        throw new Error("Failed to update profile picture");
      }

      const updated = await response.json();
      setProfile(updated);
      Alert.alert("Updated", "Your profile picture has been changed.");
    } catch (err) {
      console.error("Error updating profile picture", err);
      Alert.alert(
        "Error",
        "We couldn’t update your profile picture. Please try again."
      );
    } finally {
      setUpdatingPicture(false);
    }
  };

  /**
   * Enforce:
   * - videos <= 60 seconds
   * - videos <= ~720p (max dimension <= 1280)
   * We still recommend server-side validation, but this protects the app a bit.
   */
  const handleAddMedia = async () => {
    if (!token) return;

    const { status } =
      await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Permission needed",
        "We need access to your photos and videos to add media."
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      quality: 0.8,
    });

    if (result.canceled) return;

    const asset = result.assets && result.assets[0];
    if (!asset) return;

    const isVideo =
      asset.type === "video" ||
      (asset.uri && asset.uri.toLowerCase().endsWith(".mp4"));

    if (isVideo) {
      const durationSeconds = asset.duration || 0;
      const maxDim = Math.max(
        asset.width || 0,
        asset.height || 0
      );

      if (durationSeconds > 60) {
        Alert.alert(
          "Video too long",
          "Please choose a video that is at most 1 minute long."
        );
        return;
      }

      if (maxDim > 1280) {
        Alert.alert(
          "Resolution too high",
          "Please choose a video with resolution up to 720p."
        );
        return;
      }
    }

    const formData = new FormData();
    const fieldName = isVideo ? "video" : "image";

    formData.append(fieldName, {
      uri: asset.uri,
      name: isVideo ? "upload.mp4" : "upload.jpg",
      type: isVideo ? "video/mp4" : "image/jpeg",
    });

    if (newUploadCaption.trim().length > 0) {
      formData.append("caption", newUploadCaption.trim());
    }

    setUploadingMedia(true);
    try {
      const response = await fetch(
        buildApiUrl("/users/me/uploads/"),
        {
          method: "POST",
          headers: {
            Authorization: `Token ${token}`,
            Accept: "application/json",
          },
          body: formData,
        }
      );

      if (!response.ok) {
        const text = await response.text();
        console.warn(
          "Upload failed:",
          response.status,
          text
        );
        throw new Error("Failed to upload media");
      }

      await response.json(); // we don't really need the body
      setNewUploadCaption("");
      await loadUploads(); // refresh list
      Alert.alert("Uploaded", "Your media has been added.");
    } catch (err) {
      console.error("Error uploading media", err);
      Alert.alert(
        "Error",
        "We couldn’t upload your media. Please try again."
      );
    } finally {
      setUploadingMedia(false);
    }
  };

  /**
   * Best-effort location autofill using device GPS.
   * This does NOT use IP/cookies; it uses the phone’s location, which is
   * usually more accurate and is the standard Expo way.
   * You can later replace this with a backend-powered IP lookup if you prefer.
   */
  const handleDetectLocation = async () => {
    try {
      const { status } =
        await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        Alert.alert(
          "Permission needed",
          "We need access to your location to auto-fill the city."
        );
        return;
      }

      const position = await Location.getCurrentPositionAsync({});
      const places = await Location.reverseGeocodeAsync(
        position.coords
      );
      const place = places[0];

      const city =
        place.city ||
        place.subregion ||
        place.region ||
        "";
      const country = place.country || "";

      const formatted = [city, country]
        .filter(Boolean)
        .join(", ");

      if (!formatted) {
        Alert.alert(
          "Couldn’t detect",
          "We couldn’t determine your city. Please type it manually."
        );
        return;
      }

      setLocation(formatted);
    } catch (err) {
      console.error("Location detection error", err);
      Alert.alert(
        "Error",
        "We couldn’t detect your location. Please type it manually."
      );
    }
  };

  /**
   * Future-ready navigation. This tries to navigate to the given route name
   * if it exists in the navigation state. If not, we show a “Coming soon”
   * alert instead of throwing or silently doing nothing.
   *
   * Later, once you register screens with names:
   *  - "GlobalFeed"
   *  - "LiveEvents"
   *  - "Bookings"
   * this will start working automatically without touching this file.
   */
  const navigateIfAvailable = (routeName) => {
    try {
      const state = navigation.getState?.();
      const routeNames = state?.routeNames || [];

      if (routeNames.includes(routeName)) {
        navigation.navigate(routeName);
      } else {
        Alert.alert(
          "Coming soon",
          "This screen isn’t wired into the app yet."
        );
      }
    } catch (err) {
      console.warn(
        "Navigation check failed, falling back to alert.",
        err
      );
      Alert.alert(
        "Coming soon",
        "This screen isn’t wired into the app yet."
      );
    }
  };

  // -------------------------------------------------------------------------
  // Derived display helpers
  // -------------------------------------------------------------------------

  const profileInitial =
    (profile?.username || "?").charAt(0).toUpperCase();

  const hasUploads = uploads && uploads.length > 0;

  const approvalBadges = [];
  if (isPotentialClient) {
    approvalBadges.push(
      <StatusBadge
        key="potentialClient"
        tone="warning"
        label="Potential client"
      />
    );
  }
  if (profile?.client_approved) {
    approvalBadges.push(
      <StatusBadge
        key="clientApproved"
        tone="positive"
        label="Client approved"
      />
    );
  }
  if (profile?.performer_blacklisted) {
    approvalBadges.push(
      <StatusBadge
        key="performerBlacklisted"
        tone="danger"
        label="Performer blacklisted"
      />
    );
  }
  if (profile?.client_blacklisted) {
    approvalBadges.push(
      <StatusBadge
        key="clientBlacklisted"
        tone="danger"
        label="Client blacklisted"
      />
    );
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (!token) {
    // Should not normally happen – guarded by Auth flow – but nice to be safe.
    return (
      <View style={styles.loadingFullScreen}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={styles.loadingText}>
          Please log in again.
        </Text>
      </View>
    );
  }

  if (loadingProfile) {
    return (
      <View style={styles.loadingFullScreen}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={styles.loadingText}>
          Loading your profile…
        </Text>
      </View>
    );
  }

  if (!profile) {
    return (
      <View style={styles.loadingFullScreen}>
        <Text style={styles.loadingText}>
          No profile data available.
        </Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      {/* Split background (black / cream) */}
      <View style={styles.splitBackground}>
        <View style={styles.leftBackground} />
        <View style={styles.rightBackground} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Screen title */}
        <View style={styles.headerRow}>
          <Text style={styles.screenTitle}>Profile</Text>
          {/* Room for small app-level badge / score later if you like */}
        </View>

        {/* Main profile card */}
        <View style={styles.profileCard}>
          {/* Profile picture circle */}
          <TouchableOpacity
            onPress={handlePickProfilePicture}
            style={styles.profilePictureContainer}
            activeOpacity={0.8}
          >
            <View style={styles.profilePictureCircle}>
              {/* Show whatever the backend sends: either a computed
                 profile_picture_url or the raw profile_picture field.
                 Style names must match the StyleSheet definitions. */}
              {avatarUrl ? (
                <Image source={{ uri: avatarUrl }} style={styles.profilePictureImage} />
              ) : (
                <View style={styles.profilePictureCircle}>
                  <Text style={styles.profilePictureInitial}>
                    {(profile?.username || "U").charAt(0).toUpperCase()}
                  </Text>
                </View>
              )}
            </View>

            <Text style={styles.profilePictureHint}>
              {updatingPicture
                ? "Updating picture…"
                : "Tap to change picture"}
            </Text>
          </TouchableOpacity>

          {/* Name + profession */}
          <View style={styles.nameBlock}>
            <Text
              style={styles.profileName}
              numberOfLines={1}
            >
              {profile.username}
            </Text>
            <Text
              style={styles.profileProfession}
              numberOfLines={1}
            >
              {profession || "Profession not set yet"}
            </Text>
          </View>

          {/* Role toggles row */}
          <View style={styles.roleToggleRow}>
            <TogglePill
              active={isPotentialClient}
              label="Potential client"
              onPress={() =>
                setIsPotentialClient((prev) => !prev)
              }
            />
            <TogglePill
              active={isPerformer}
              label="Performer"
              onPress={() =>
                setIsPerformer((prev) => !prev)
              }
            />
          </View>

          {/* Status badges (approval / blacklists) */}
          {approvalBadges.length > 0 && (
            <View style={styles.badgeRow}>{approvalBadges}</View>
          )}

          {/* Editable BIO */}
          <View style={styles.sectionBlock}>
            <Text style={styles.sectionTitle}>BIO</Text>
            <TextInput
              style={styles.multiLineInput}
              placeholder="You haven't added a bio yet."
              placeholderTextColor={COLORS.textMuted}
              multiline
              value={bio}
              onChangeText={setBio}
            />
          </View>

          {/* Editable LOCATION with "Use my location" helper */}
          <View style={styles.sectionBlock}>
            <View style={styles.sectionHeaderRow}>
              <Text style={styles.sectionTitle}>LOCATION</Text>
              <TouchableOpacity
                onPress={handleDetectLocation}
              >
                <Text style={styles.linkButtonText}>
                  Use my location
                </Text>
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.singleLineInput}
              placeholder="City, Country"
              placeholderTextColor={COLORS.textMuted}
              value={location}
              onChangeText={setLocation}
            />
          </View>

          {/* Editable PROFESSION */}
          <View style={styles.sectionBlock}>
            <Text style={styles.sectionTitle}>PROFESSION</Text>
            <TextInput
              style={styles.singleLineInput}
              placeholder="What do you do?"
              placeholderTextColor={COLORS.textMuted}
              value={profession}
              onChangeText={setProfession}
            />
          </View>

          {/* Explore links – future-ready navigation */}
          <View style={styles.sectionBlock}>
            <Text style={styles.sectionTitle}>EXPLORE</Text>
            <View style={styles.exploreRow}>
              <TouchableOpacity
                style={styles.exploreButton}
                onPress={() =>
                  navigateIfAvailable("GlobalFeed")
                }
              >
                <Text style={styles.exploreButtonText}>
                  Global feed
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.exploreButton}
                onPress={() =>
                  navigateIfAvailable("LiveEvents")
                }
              >
                <Text style={styles.exploreButtonText}>
                  Live events
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.exploreButton}
                onPress={() =>
                  navigateIfAvailable("Bookings")
                }
              >
                <Text style={styles.exploreButtonText}>
                  Bookings
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Uploads header + caption + add button */}
          <View style={styles.uploadsHeader}>
            <View>
              <Text style={styles.uploadsTitle}>
                Your uploads
              </Text>
              <Text style={styles.uploadsSubtitle}>
                (max ~1 min video, 720p – enforced later)
              </Text>
            </View>
            <TouchableOpacity
              onPress={handleAddMedia}
              style={styles.addMediaButton}
              disabled={uploadingMedia}
            >
              <Text style={styles.addMediaText}>
                {uploadingMedia ? "Uploading…" : "+ Add media"}
              </Text>
            </TouchableOpacity>
          </View>

          <TextInput
            style={styles.singleLineInput}
            placeholder="Caption for next upload (optional)"
            placeholderTextColor={COLORS.textMuted}
            value={newUploadCaption}
            onChangeText={setNewUploadCaption}
          />

          {/* Uploads list */}
          <View style={styles.uploadsListBlock}>
            {loadingUploads ? (
              <View style={styles.uploadsLoadingRow}>
                <ActivityIndicator
                  size="small"
                  color={COLORS.accent}
                />
                <Text style={styles.uploadsLoadingText}>
                  Loading your uploads…
                </Text>
              </View>
            ) : hasUploads ? (
              /* Vertical stack of full-width cards, newest first
                 (backend already sorts by -upload_date) */
              <View>
                {uploads.map((u) => (
                  <UploadCard key={u.id} upload={u} />
                ))}
              </View>
            ) : (
              <View style={styles.noUploadsBlock}>
                <Text style={styles.noUploadsText}>
                  You haven’t uploaded anything yet.
                </Text>
                <Text style={styles.noUploadsHint}>
                  Use the website for now, or Add media above for
                  in-app uploads.
                </Text>
              </View>
            )}
          </View>

          {/* Save + Logout buttons */}
          <View style={styles.actionsRow}>
            <TouchableOpacity
              style={[
                styles.primaryButton,
                savingProfile && { opacity: 0.6 },
              ]}
              onPress={handleSaveProfile}
              disabled={savingProfile}
            >
              <Text style={styles.primaryButtonText}>
                {savingProfile ? "Saving…" : "Save profile"}
              </Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={styles.logoutButton}
            onPress={logout}
          >
            <Text style={styles.logoutButtonText}>Log out</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Styles – tuned for a clean, app-native feel that still echoes your site
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  splitBackground: {
    ...StyleSheet.absoluteFillObject,
    flexDirection: "row",
  },
  leftBackground: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  rightBackground: {
    flex: 1,
    backgroundColor: COLORS.backgroundRight,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 32,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
    marginTop: 4,
  },
  screenTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },

  profileCard: {
    backgroundColor: COLORS.card,
    borderRadius: 28,
    padding: 20,
    marginTop: 8,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
    elevation: 8,
  },

  profilePictureContainer: {
    alignItems: "center",
    marginBottom: 16,
  },
  profilePictureCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 3,
    borderColor: COLORS.accent,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#222222",
    overflow: "hidden",
  },
  profilePictureImage: {
    width: "100%",
    height: "100%",
    resizeMode: "cover",
  },
  profilePictureInitial: {
    fontSize: 36,
    fontWeight: "700",
    color: COLORS.accent,
  },
  profilePictureHint: {
    marginTop: 6,
    fontSize: 12,
    color: COLORS.textMuted,
  },

  nameBlock: {
    alignItems: "center",
    marginBottom: 12,
  },
  profileName: {
    fontSize: 24,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  profileProfession: {
    marginTop: 4,
    fontSize: 16,
    color: COLORS.textSecondary,
  },

  roleToggleRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 12,
    marginTop: 8,
    flexWrap: "wrap",
  },
  togglePill: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: COLORS.accent,
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: COLORS.card,
  },
  togglePillActive: {
    backgroundColor: COLORS.accent,
  },
  togglePillText: {
    fontSize: 13,
    color: COLORS.accent,
    fontWeight: "500",
  },
  togglePillTextActive: {
    color: COLORS.textPrimary,
  },

  badgeRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  statusBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  statusBadgeText: {
    fontSize: 12,
    fontWeight: "600",
  },

  sectionBlock: {
    marginTop: 18,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: COLORS.textSecondary,
    letterSpacing: 1.1,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },

  multiLineInput: {
    marginTop: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: "#181818",
    borderWidth: 1,
    borderColor: COLORS.divider,
    minHeight: 70,
    maxHeight: 140,
    color: COLORS.textPrimary,
    textAlignVertical: "top",
    fontSize: 14,
  },
  singleLineInput: {
    marginTop: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: "#181818",
    borderWidth: 1,
    borderColor: COLORS.divider,
    color: COLORS.textPrimary,
    fontSize: 14,
  },

  exploreRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 8,
  },
  exploreButton: {
    borderRadius: 999,
    backgroundColor: COLORS.buttonDark,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  exploreButtonText: {
    color: COLORS.textPrimary,
    fontSize: 14,
    fontWeight: "500",
  },

  linkButtonText: {
    color: COLORS.accent,
    fontSize: 13,
    fontWeight: "500",
  },

  uploadsHeader: {
    marginTop: 24,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  uploadsTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  uploadsSubtitle: {
    fontSize: 12,
    marginTop: 4,
    color: COLORS.textMuted,
  },
  addMediaButton: {
    alignSelf: "flex-start",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: COLORS.accent,
  },
  addMediaText: {
    color: COLORS.textPrimary,
    fontWeight: "600",
    fontSize: 13,
  },

  uploadsListBlock: {
    marginTop: 10,
  },
  uploadsLoadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  uploadsLoadingText: {
    color: COLORS.textSecondary,
    fontSize: 13,
  },
  noUploadsBlock: {
    marginTop: 6,
  },
  noUploadsText: {
    color: COLORS.textSecondary,
    fontSize: 14,
  },
  noUploadsHint: {
    color: COLORS.textMuted,
    fontSize: 12,
    marginTop: 2,
  },

  /* Full-width card instead of 140px thumbnail, matching the website */
  uploadCard: {
    width: "100%",
    padding: 10,
    marginBottom: 16,
    borderRadius: 14,
    backgroundColor: "#181818",
    borderWidth: 1,
    borderColor: COLORS.divider,
  },
  /* Portrait-friendly preview that mirrors the website's large photos */
  uploadImage: {
    width: "100%",
    aspectRatio: 3 / 4,       // portrait like the website
    borderRadius: 12,
    marginBottom: 8,
  },
  uploadTypePill: {
    alignSelf: "flex-start",
    borderRadius: 999,
    backgroundColor: COLORS.chipBackground,
    paddingHorizontal: 8,
    paddingVertical: 2,
    marginBottom: 4,
  },
  uploadTypeText: {
    color: COLORS.textSecondary,
    fontSize: 10,
    fontWeight: "600",
    textTransform: "uppercase",
  },
  uploadCaption: {
    color: COLORS.textPrimary,
    fontSize: 13,
    marginTop: 2,
  },
  uploadDateText: {
    marginTop: 6,
    color: COLORS.textMuted,
    fontSize: 11,
  },

  actionsRow: {
    marginTop: 24,
  },
  primaryButton: {
    borderRadius: 999,
    backgroundColor: COLORS.accent,
    paddingVertical: 12,
    alignItems: "center",
  },
  primaryButtonText: {
    color: COLORS.textPrimary,
    fontSize: 15,
    fontWeight: "600",
  },

  logoutButton: {
    marginTop: 14,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: COLORS.divider,
    paddingVertical: 11,
    alignItems: "center",
  },
  logoutButtonText: {
    color: COLORS.textSecondary,
    fontSize: 14,
  },

  loadingFullScreen: {
    flex: 1,
    backgroundColor: COLORS.background,
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    marginTop: 8,
    color: COLORS.textSecondary,
  },

  uploadThumbnail: {
    width: 220,
    height: 140,
    borderRadius: 18,
    marginBottom: 8,
  },

  uploadFallback: {
    width: 220,
    height: 140,
    borderRadius: 18,
    marginBottom: 8,
    backgroundColor: "#2a2a2a",
    alignItems: "center",
    justifyContent: "center",
  },

  uploadFallbackText: {
    color: COLORS.textMuted,
    fontSize: 13,
  },

  uploadDateText: {
    color: COLORS.textMuted,
    fontSize: 11,
  },
  uploadMeta: {
    marginTop: 6,
    color: COLORS.textMuted,
    fontSize: 11,
  },

});
