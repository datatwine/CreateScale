import React, { useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets, SafeAreaView } from "react-native-safe-area-context";
import { useNavigation, useFocusEffect } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import { Ionicons } from "@expo/vector-icons"; // only once
import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";
import { uploadMedia } from "../api/upload";
import { kycLabel, kycColor, shouldShowPayoutsLink, shouldShowPaymentsLink } from "../utils/settingsDrawer";
import { isUnauthorized } from "../utils/session";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";

// ---------------------------------------------------------------------------
// Client-side media compression helpers
//
// shrinkImage: hardware-backed resize/re-encode via expo-image-manipulator.
//   Per-kind max dimension. Output JPEG quality 0.82. Idempotent if the image
//   is already smaller than maxWidth.
//
// Note: Video compression removed for Expo Go compatibility.
//   For production, use eas build with a custom development client.
//
// Both are wrapped in try/catch by callers: on any failure they fall back
// to the original URI so the upload still works.
// ---------------------------------------------------------------------------

async function shrinkImage(uri, maxWidth) {
  const out = await ImageManipulator.manipulateAsync(
    uri,
    [{ resize: { width: maxWidth } }],
    { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG }
  );
  return out.uri;
}

// Lazy-load so Expo Go (no native modules) skips compression gracefully;
// EAS production builds get full hardware-accelerated compression.
let VideoCompressor = null;
try {
  VideoCompressor = require("react-native-compressor").Video;
} catch {
  // Expo Go — native module unavailable, compression will be skipped
}

async function compressVideo(uri) {
  if (!VideoCompressor) return uri;
  return await VideoCompressor.compress(
    uri,
    { compressionMethod: "manual", maxSize: 1920, bitrate: 4_000_000 },
    () => {},
  );
}

function buildApiUrl(path) {
  const trimmedBase = API_BASE_URL.replace(/\/+$/, "");
  const trimmedPath = path.replace(/^\/+/, "");
  return `${trimmedBase}/${trimmedPath}`;
}

const makeMediaUrl = (pathOrUrl) => {
  if (!pathOrUrl) return null;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  const backendRoot = API_BASE_URL.replace(/\/api\/?$/, "");
  if (pathOrUrl.startsWith("/")) return backendRoot + pathOrUrl;
  return `${backendRoot}/${pathOrUrl}`;
};

function StatusBadge({ label, tone = "default" }) {
  let backgroundColor = COLORS.cream;
  let textColor = COLORS.textSecondary;
  if (tone === "positive") {
    backgroundColor = COLORS.successBg;
    textColor = COLORS.successText;
  } else if (tone === "warning") {
    backgroundColor = COLORS.infoBg;
    textColor = COLORS.info;
  } else if (tone === "danger") {
    backgroundColor = COLORS.dangerBg;
    textColor = COLORS.dangerText;
  }
  return (
    <View style={[styles.statusBadge, { backgroundColor }]}>
      <Text style={[styles.statusBadgeText, { color: textColor }]}>{label}</Text>
    </View>
  );
}

function UploadGridItem({ upload, onPress }) {
  const imageUri = makeMediaUrl(upload.image_url || upload.image);
  const videoUri = !imageUri ? makeMediaUrl(upload.video_url || upload.video) : null;
  const hasImage = !!imageUri;
  const hasVideo = !hasImage && !!videoUri;

  return (
    <View style={styles.gridItem}>
      <TouchableOpacity style={styles.gridItemInner} onPress={onPress} activeOpacity={0.8}>
        {hasImage ? (
          <Image source={{ uri: imageUri }} style={styles.gridImage} resizeMode="cover" />
        ) : hasVideo ? (
          <View style={styles.gridVideoFallback}>
            <Ionicons name="videocam" size={20} color={COLORS.textMuted} />
          </View>
        ) : (
          <View style={styles.gridVideoFallback}>
            <Ionicons name="image-outline" size={20} color={COLORS.textMuted} />
          </View>
        )}
        {upload.caption ? (
          <Text style={styles.gridCaption} numberOfLines={1}>{upload.caption}</Text>
        ) : null}
      </TouchableOpacity>
    </View>
  );
}

function PreviewModal({ visible, upload, onClose, onEdit, onDelete }) {
  const { width: screenWidth, height: screenHeight } = useWindowDimensions();
  const [editCaption, setEditCaption] = useState("");
  const [showOptions, setShowOptions] = useState(false);
  const [editing, setEditing] = useState(false);
  const mediaHeight = screenHeight * 0.7;

  useEffect(() => {
    if (upload) {
      setEditCaption(upload.caption || "");
      setEditing(false);
      setShowOptions(false);
    }
  }, [upload]);

  if (!upload) return null;

  const imageUri = makeMediaUrl(upload.image_url || upload.image);
  const videoUri = !imageUri ? makeMediaUrl(upload.video_url || upload.video) : null;
  const hasImage = !!imageUri;
  const hasVideo = !hasImage && !!videoUri;

  const handleSaveCaption = () => {
    setEditing(false);
    onClose();
    onEdit(upload.id, editCaption);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableOpacity style={styles.previewOverlay} activeOpacity={1} onPress={onClose}>
        <TouchableOpacity activeOpacity={1} onPress={() => {}} style={styles.previewContent}>
          {hasImage ? (
            <Image
              source={{ uri: imageUri }}
              style={[styles.previewMedia, { width: screenWidth, height: mediaHeight }]}
              resizeMode="contain"
            />
          ) : hasVideo ? (
            <View style={[styles.previewVideoFallback, { width: screenWidth - 32 }]}>
              <Ionicons name="videocam" size={48} color={COLORS.textMuted} />
              <Text style={styles.previewVideoText}>Video</Text>
            </View>
          ) : null}

          {editing ? (
            <View style={styles.previewEditWrap}>
              <TextInput
                style={styles.previewEditInput}
                value={editCaption}
                onChangeText={setEditCaption}
                multiline
                autoFocus
                placeholder="Write a caption..."
                placeholderTextColor={COLORS.placeholder}
              />
              <View style={styles.previewEditBtns}>
                <TouchableOpacity onPress={handleSaveCaption}>
                  <Text style={{ color: COLORS.accent, fontWeight: "600", fontSize: 14 }}>Save</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { setEditing(false); setEditCaption(upload.caption || ""); }}>
                  <Text style={{ color: COLORS.textMuted, fontSize: 14 }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : editCaption ? (
            <Text style={styles.previewCaption}>{editCaption}</Text>
          ) : null}
        </TouchableOpacity>

        <TouchableOpacity style={styles.previewClose} onPress={onClose}>
          <Ionicons name="close" size={24} color={COLORS.ink} />
        </TouchableOpacity>

        <TouchableOpacity style={styles.previewMenu} onPress={() => setShowOptions(v => !v)}>
          <Ionicons name="ellipsis-vertical" size={20} color={COLORS.ink} />
        </TouchableOpacity>

        {showOptions && (
          <View style={styles.previewOptionsCard}>
            <TouchableOpacity
              style={styles.previewOption}
              onPress={() => { setShowOptions(false); setEditing(true); }}
            >
              <Text style={styles.previewOptionText}>Edit caption</Text>
            </TouchableOpacity>
            <View style={styles.previewOptionDivider} />
            <TouchableOpacity
              style={styles.previewOption}
              onPress={() => { setShowOptions(false); onClose(); onDelete(upload.id); }}
            >
              <Text style={[styles.previewOptionText, { color: COLORS.dangerBright }]}>Delete</Text>
            </TouchableOpacity>
            <View style={styles.previewOptionDivider} />
            <TouchableOpacity
              style={styles.previewOption}
              onPress={() => setShowOptions(false)}
            >
              <Text style={[styles.previewOptionText, { color: COLORS.textMuted }]}>Cancel</Text>
            </TouchableOpacity>
          </View>
        )}
      </TouchableOpacity>
    </Modal>
  );
}

export default function ProfileScreen() {
  const navigation = useNavigation();
  const { token, logout } = useContext(AuthContext);

  const [profile, setProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  // Profile picture / cover photo upload in progress flags
  const [updatingPicture, setUpdatingPicture] = useState(false);
  const [updatingCover, setUpdatingCover] = useState(false);

  // Settings drawer visibility
  const [drawerVisible, setDrawerVisible] = useState(false);
  const insets = useSafeAreaInsets();
  const { width: windowWidth } = useWindowDimensions();

  // Drawer slides in from the right (1 = hidden off-screen, 0 = in place)
  const drawerAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (drawerVisible) {
      drawerAnim.setValue(1);
      Animated.spring(drawerAnim, {
        toValue: 0,
        useNativeDriver: true,
        speed: 20,
        bounciness: 5,
      }).start();
    }
  }, [drawerVisible, drawerAnim]);

  const closeDrawer = useCallback(() => {
    Animated.timing(drawerAnim, {
      toValue: 1,
      duration: 200,
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (finished) setDrawerVisible(false);
    });
  }, [drawerAnim]);

  // --- Uploads (media gallery) ---------------------------------------------
  const [uploads, setUploads] = useState([]);
  const [loadingUploads, setLoadingUploads] = useState(true);
  const [uploadingMedia, setUploadingMedia] = useState(false);
  const [previewUpload, setPreviewUpload] = useState(null);
  const initialLoadDone = useRef(false);

  const avatarUrl = makeMediaUrl(
    profile?.profile_picture_url || profile?.profile_picture || null
  );

  const loadProfile = useCallback(async (silent = false) => {
    if (!token) return;
    if (!silent) setLoadingProfile(true);
    try {
      const response = await fetch(buildApiUrl("/users/me/"), {
        method: "GET",
        headers: { Authorization: `Token ${token}`, Accept: "application/json" },
      });
      if (!response.ok) {
        // For debugging JSON parse problems:
        const text = await response.text();
        console.warn("Profile load failed:", response.status, text);
        if (isUnauthorized(response.status)) {
          // Stale/invalid token — bounce back to Login instead of getting
          // stuck showing "couldn't load your profile" forever.
          await logout();
          return;
        }
        throw new Error("Failed to load profile");
      }
      const data = await response.json();
      setProfile(data);
    } catch (err) {
      console.error("Error loading profile", err);
      if (!silent) Alert.alert("Error", "Could not load your profile.");
    } finally {
      setLoadingProfile(false);
    }
  }, [token, logout]);

  const loadUploads = useCallback(async (silent = false) => {
    if (!token) return;
    if (!silent) setLoadingUploads(true);
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
        if (isUnauthorized(response.status)) {
          await logout();
          return;
        }
        throw new Error("Failed to load uploads");
      }
      const data = await response.json();
      setUploads(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error loading uploads", err);
    } finally {
      setLoadingUploads(false);
    }
  }, [token, logout]);

  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      if (!initialLoadDone.current) {
        initialLoadDone.current = true;
        loadProfile();
        loadUploads();
      } else {
        loadProfile(true);
        loadUploads(true);
      }
    }, [token, loadProfile, loadUploads])
  );

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

    // Client-side compress to 512px avatar (hardware-accelerated). On any
    // failure, fall back to the original asset URI so upload still works.
    let avatarUri = asset.uri;
    try {
      avatarUri = await shrinkImage(asset.uri, 512);
    } catch (e) {
      console.warn("avatar shrink failed, uploading original", e);
    }

    const formData = new FormData();
    formData.append("profile_picture", {
      uri: avatarUri,
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

  const handlePickCoverPhoto = async () => {
    if (!token) return;
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "We need access to your photos to set a cover photo.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [16, 9],
      quality: 0.85,
    });
    if (result.canceled) return;
    const asset = result.assets && result.assets[0];
    if (!asset) return;

    let coverUri = asset.uri;
    try {
      coverUri = await shrinkImage(asset.uri, 1920);
    } catch (e) {
      console.warn("cover shrink failed, uploading original", e);
    }

    const formData = new FormData();
    formData.append("cover_photo", { uri: coverUri, name: "cover.jpg", type: "image/jpeg" });

    setUpdatingCover(true);
    try {
      const response = await fetch(buildApiUrl("/users/me/"), {
        method: "PATCH",
        headers: { Authorization: `Token ${token}`, Accept: "application/json" },
        body: formData,
      });
      if (!response.ok) throw new Error("Failed to update cover photo");
      const updated = await response.json();
      setProfile(updated);
      Alert.alert("Updated", "Your cover photo has been changed.");
    } catch (err) {
      console.error("Error updating cover photo", err);
      Alert.alert("Error", "We couldn't update your cover photo. Please try again.");
    } finally {
      setUpdatingCover(false);
    }
  };

  async function handleDeleteUpload(uploadId) {
    Alert.alert("Delete upload?", "This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete", style: "destructive",
        onPress: async () => {
          try {
            const res = await fetch(`${API_BASE_URL}/users/me/uploads/${uploadId}/`, {
              method: "DELETE",
              headers: { Authorization: `Token ${token}` },
            });
            if (res.ok) {
              setUploads((prev) => prev.filter((u) => u.id !== uploadId));
            } else {
              Alert.alert("Error", "Could not delete upload.");
            }
          } catch {
            Alert.alert("Error", "Network error.");
          }
        },
      },
    ]);
  }

  async function handleEditCaption(uploadId, newCaption) {
    try {
      const res = await fetch(`${API_BASE_URL}/users/me/uploads/${uploadId}/`, {
        method: "PATCH",
        headers: {
          Authorization: `Token ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ caption: newCaption }),
      });
      if (res.ok) {
        const updated = await res.json();
        setUploads((prev) =>
          prev.map((u) => (u.id === uploadId ? { ...u, caption: updated.caption } : u))
        );
      } else {
        Alert.alert("Error", "Could not update caption.");
      }
    } catch {
      Alert.alert("Error", "Network error.");
    }
  }

  const handleAddMedia = async () => {
    if (!token) return;
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "We need access to your photos.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      quality: 0.8,
      videoExportPreset: ImagePicker.VideoExportPreset?.H264_1280x720,
    });
    if (result.canceled) return;
    const asset = result.assets?.[0];
    if (!asset) return;

    const isVideo = asset.type === "video" || asset.uri?.toLowerCase().endsWith(".mp4");
    if (isVideo) {
      const durationSeconds = asset.duration || 0;
      if (durationSeconds > 60) {
        Alert.alert("Video too long", "Please choose a video at most 1 minute.");
        return;
      }
    }

    setUploadingMedia(true);
    let finalUri = asset.uri;
    try {
      finalUri = isVideo ? await compressVideo(asset.uri) : await shrinkImage(asset.uri, 1080);
    } catch (e) {
      console.warn("media compress failed", e);
    }

    try {
      await uploadMedia({
        token,
        fileUri: finalUri,
        fileName: isVideo ? "upload.mp4" : "upload.jpg",
        contentType: isVideo ? "video/mp4" : "image/jpeg",
        caption: "",
      });
      await loadUploads();
      Alert.alert("Uploaded", "Your media has been added.");
    } catch (err) {
      console.error("Error uploading media", err);
      Alert.alert("Error", "Could not upload media.");
    } finally {
      setUploadingMedia(false);
    }
  };

  const isPerformer = profile?.is_performer || false;
  const isPotentialClient = profile?.is_potential_client || false;

  if (!token || loadingProfile) {
    return (
      <View style={styles.loadingFullScreen}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        {loadingProfile && <Text style={styles.loadingText}>Loading your profile…</Text>}
      </View>
    );
  }

  if (!profile) {
    return (
      <View style={styles.loadingFullScreen}>
        <Text style={styles.loadingText}>No profile data available.</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.topRow}>
          <Text style={styles.screenTitle}>Profile</Text>
          <TouchableOpacity onPress={() => setDrawerVisible(true)} style={styles.gearButton}>
            <Ionicons name="settings-outline" size={24} color={COLORS.textPrimary} />
          </TouchableOpacity>
        </View>

        {/* Cover photo banner */}
        <TouchableOpacity
          onPress={handlePickCoverPhoto}
          activeOpacity={0.85}
          style={styles.coverBanner}
        >
          {profile?.cover_photo_url ? (
            <Image
              source={{ uri: makeMediaUrl(profile.cover_photo_url) }}
              style={styles.coverBannerImage}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.coverBannerEmpty}>
              <Ionicons name="image-outline" size={22} color={COLORS.textMuted} />
              <Text style={styles.coverBannerHint}>
                {updatingCover ? "Updating…" : "Add cover photo"}
              </Text>
            </View>
          )}
          {profile?.cover_photo_url ? (
            <View style={styles.coverBannerOverlay}>
              <Text style={styles.coverBannerHint}>
                {updatingCover ? "Updating…" : "✎ Change cover photo"}
              </Text>
            </View>
          ) : null}
        </TouchableOpacity>

        <View style={styles.profileHeader}>
          <View style={styles.profilePictureContainer}>
            <TouchableOpacity
              onPress={handlePickProfilePicture}
              style={styles.avatarCircle}
              activeOpacity={0.8}
            >
              {avatarUrl ? (
                <Image source={{ uri: avatarUrl }} style={styles.avatarImage} />
              ) : (
                <Text style={styles.avatarInitial}>
                  {(profile.username || "U").charAt(0).toUpperCase()}
                </Text>
              )}
            </TouchableOpacity>
            <Text style={styles.profilePictureHint}>
              {updatingPicture ? "Updating picture…" : "Tap to change"}
            </Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName} numberOfLines={1}>{profile.username}</Text>
            {profile.profession ? (
              <Text style={styles.profileProfession} numberOfLines={1}>{profile.profession}</Text>
            ) : null}
            {profile.location ? (
              <Text style={styles.profileLocation} numberOfLines={1}>{profile.location}</Text>
            ) : null}
          </View>
        </View>

        {profile.bio ? (
          <Text style={styles.bioText}>{profile.bio}</Text>
        ) : null}

        <View style={styles.badgeRow}>
          {isPotentialClient && <StatusBadge tone="warning" label="Potential client" />}
          {isPerformer && <StatusBadge tone="positive" label="Performer" />}
          {profile.client_approved && <StatusBadge tone="positive" label="Client approved" />}
          {profile.performer_blacklisted && <StatusBadge tone="danger" label="Performer blacklisted" />}
          {profile.client_blacklisted && <StatusBadge tone="danger" label="Client blacklisted" />}
        </View>

        <View style={styles.divider} />

        <View style={styles.uploadsSection}>
          <View style={styles.uploadsHeader}>
            <Text style={styles.uploadsTitle}>Uploads</Text>
            <PressableStamp
              onPress={handleAddMedia}
              disabled={uploadingMedia}
              stampOffset={3}
              borderRadius={999}
              borderColor={COLORS.ink}
              borderWidth={2}
              style={styles.addMediaBtn}
            >
              <Ionicons name="add" size={18} color={COLORS.textPrimary} />
              <Text style={styles.addMediaText}>{uploadingMedia ? "Uploading…" : "Add"}</Text>
            </PressableStamp>
          </View>

          {loadingUploads ? (
            <View style={styles.uploadsLoadingRow}>
              <ActivityIndicator size="small" color={COLORS.accent} />
              <Text style={styles.uploadsLoadingText}>Loading uploads…</Text>
            </View>
          ) : uploads.length > 0 ? (
            <View style={styles.gridContainer}>
              {uploads.map((u) => (
                <UploadGridItem
                  key={u.id}
                  upload={u}
                  onPress={() => setPreviewUpload(u)}
                />
              ))}
            </View>
          ) : (
            <View style={styles.noUploadsBlock}>
              <Ionicons name="image-outline" size={40} color={COLORS.textMuted} />
              <Text style={styles.noUploadsText}>No uploads yet</Text>
            </View>
          )}
        </View>
      </ScrollView>

      <PreviewModal
        visible={!!previewUpload}
        upload={previewUpload}
        onClose={() => setPreviewUpload(null)}
        onEdit={handleEditCaption}
        onDelete={handleDeleteUpload}
      />

      {/* ── Settings drawer ── */}
      <Modal
        visible={drawerVisible}
        transparent
        animationType="none"
        onRequestClose={closeDrawer}
      >
        <TouchableOpacity
          style={styles.drawerOverlay}
          activeOpacity={1}
          onPress={closeDrawer}
        />
        <Animated.View style={[styles.drawerPanel, {
          paddingTop: insets.top + 16,
          paddingBottom: insets.bottom + 16,
          transform: [{
            translateX: drawerAnim.interpolate({
              inputRange: [0, 1],
              outputRange: [0, windowWidth],
            }),
          }],
        }]}>
          {/* Header */}
          <View style={styles.drawerHeader}>
            <Text style={styles.drawerTitle}>Settings</Text>
            <TouchableOpacity onPress={closeDrawer}>
              <Ionicons name="close" size={22} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Account */}
          <View style={styles.drawerSection}>
            <Text style={styles.drawerSectionTitle}>Account</Text>
            <TouchableOpacity
              style={styles.drawerLink}
              onPress={() => {
                  closeDrawer();
                  navigation.navigate("EditProfile");
              }}
            >
              <Text style={styles.drawerLinkText}>✎  Edit profile</Text>
            </TouchableOpacity>
          </View>

          {/* Payment Setup — performers only */}
          {profile?.is_performer && (
            <View style={styles.drawerSection}>
              <Text style={styles.drawerSectionTitle}>Payment Setup</Text>

              {/* KYC status badge */}
              <View style={[
                styles.kycBadge,
                { backgroundColor: KYC_BADGE_BG[kycColor(profile?.razorpay_kyc_status)] },
              ]}>
                <Text style={[
                  styles.kycBadgeText,
                  { color: KYC_BADGE_TEXT[kycColor(profile?.razorpay_kyc_status)] },
                ]}>
                  {kycLabel(profile?.razorpay_kyc_status)}
                </Text>
              </View>

              {/* Fee */}
              {profile?.performer_fee ? (
                <Text style={styles.drawerDetail}>
                  Standard fee: <Text style={styles.drawerDetailBold}>₹{profile.performer_fee}</Text>
                </Text>
              ) : null}

              {/* Masked bank */}
              {profile?.bank_account_last4 ? (
                <Text style={styles.drawerDetail}>
                  Bank: {profile.bank_ifsc}{"  "}
                  <Text style={styles.drawerDetailBold}>
                    ****{profile.bank_account_last4}
                  </Text>
                </Text>
              ) : null}

              <TouchableOpacity
                style={styles.drawerOutlineBtn}
                onPress={() => {
                  closeDrawer();
                  navigation.navigate("PaymentDetails");
                }}
              >
                <Text style={styles.drawerOutlineBtnText}>
                  {profile?.razorpay_account_id ? "Edit payment details" : "Set up payment details"}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Payment history — only for the roles that generate it */}
          {(shouldShowPayoutsLink(profile) || shouldShowPaymentsLink(profile)) && (
            <View style={styles.drawerSection}>
              <Text style={styles.drawerSectionTitle}>Your Payments</Text>

              {shouldShowPayoutsLink(profile) && (
                <TouchableOpacity
                  style={styles.drawerLink}
                  onPress={() => {
                    closeDrawer();
                    navigation.navigate("PerformerPayouts");
                  }}
                >
                  <Text style={styles.drawerLinkText}>📥  View payouts received</Text>
                </TouchableOpacity>
              )}

              {shouldShowPaymentsLink(profile) && (
                <TouchableOpacity
                  style={styles.drawerLink}
                  onPress={() => {
                    closeDrawer();
                    navigation.navigate("ClientPayments");
                  }}
                >
                  <Text style={styles.drawerLinkText}>📤  View payments made</Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </Animated.View>
      </Modal>
    </SafeAreaView>
  );
}

// KYC badge colour maps (token → COLORS key), matching the web CSS classes
const KYC_BADGE_BG = {
  green: COLORS.successBg,
  amber: COLORS.cream,
  red:   COLORS.dangerBg,
  grey:  COLORS.neutralBg,
};
const KYC_BADGE_TEXT = {
  green: COLORS.successText,
  amber: COLORS.accentDark,
  red:   COLORS.dangerText,
  grey:  COLORS.textSecondary,
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.black,
  },
  scrollContent: {
    paddingHorizontal: 16,
    paddingBottom: 32,
    backgroundColor: COLORS.background,
    flexGrow: 1,
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 4,
    marginBottom: 20,
  },
  screenTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  profileHeader: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 16,
  },
  profileCard: {
    backgroundColor: COLORS.card,
    borderRadius: 28,
    padding: 20,
    marginTop: 8,
    shadowColor: COLORS.black,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
    elevation: 8,
  },

  coverBanner: {
    width: "100%",
    height: 120,
    borderRadius: 16,
    overflow: "hidden",
    marginBottom: 16,
    backgroundColor: COLORS.darkSurface,
  },
  coverBannerImage: {
    width: "100%",
    height: "100%",
  },
  coverBannerEmpty: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: COLORS.divider,
    borderRadius: 16,
    borderStyle: "dashed",
  },
  coverBannerOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.35)",
    alignItems: "center",
    justifyContent: "flex-end",
    paddingBottom: 8,
  },
  coverBannerHint: {
    fontSize: 12,
    color: COLORS.textMuted,
  },

  profilePictureContainer: {
    alignItems: "center",
    marginBottom: 16,
    marginRight: 14,
  },
  profilePictureHint: {
    marginTop: 4,
    fontSize: 11,
    color: COLORS.textMuted,
  },
  avatarCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 2,
    borderColor: COLORS.accent,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.cream,
    overflow: "hidden",
  },
  avatarImage: {
    width: "100%",
    height: "100%",
    resizeMode: "cover",
  },
  avatarInitial: {
    fontSize: 24,
    fontWeight: "700",
    color: COLORS.accent,
  },
  profileInfo: {
    flex: 1,
    marginLeft: 14,
  },
  profileName: {
    fontSize: 20,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  profileProfession: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  profileLocation: {
    fontSize: 13,
    color: COLORS.textMuted,
    marginTop: 1,
  },
  bioText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    lineHeight: 20,
    marginBottom: 12,
  },
  badgeRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 16,
  },
  statusBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1.5,
    borderColor: COLORS.ink,
  },
  statusBadgeText: {
    fontSize: 12,
    fontWeight: "600",
  },
  divider: {
    height: 1,
    backgroundColor: COLORS.divider,
    marginBottom: 20,
  },
  uploadsSection: {
    marginBottom: 24,
  },
  uploadsHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  uploadsTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  addMediaBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: COLORS.accent,
  },
  addMediaText: {
    color: COLORS.textPrimary,
    fontWeight: "600",
    fontSize: 13,
  },
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
    overflow: "hidden",
    position: "relative",
    borderWidth: 1.5,
    borderColor: COLORS.ink,
  },
  gridImage: {
    width: "100%",
    height: "100%",
  },
  gridVideoFallback: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.cream,
  },
  gridCaption: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "rgba(0,0,0,0.6)",
    color: COLORS.white,
    fontSize: 10,
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  uploadsLoadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 12,
  },
  uploadsLoadingText: {
    color: COLORS.textSecondary,
    fontSize: 13,
  },
  noUploadsBlock: {
    alignItems: "center",
    marginTop: 24,
    gap: 8,
  },
  noUploadsText: {
    color: COLORS.textMuted,
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
    backgroundColor: COLORS.darkCard,
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
    backgroundColor: COLORS.cream,
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

  // --- Gear button ---
  gearButton: {
    padding: 4,
  },

  // --- Settings drawer ---
  drawerOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  drawerPanel: {
    position: "absolute",
    right: 0,
    top: 0,
    bottom: 0,
    width: "85%",
    backgroundColor: COLORS.background,
    padding: 24,
    shadowColor: COLORS.black,
    shadowOffset: { width: -4, height: 0 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 10,
  },
  drawerHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 24,
  },
  drawerTitle: {
    fontSize: 20,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  drawerSection: {
    marginBottom: 24,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  drawerSectionTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: COLORS.textPrimary,
    marginBottom: 12,
  },
  kycBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    marginBottom: 8,
  },
  kycBadgeText: {
    fontSize: 13,
    fontWeight: "700",
  },
  drawerDetail: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginVertical: 4,
  },
  drawerDetailBold: {
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  drawerOutlineBtn: {
    marginTop: 10,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1.5,
    borderColor: COLORS.warning,
    borderRadius: 8,
    alignSelf: "flex-start",
  },
  drawerOutlineBtnText: {
    color: COLORS.warning,
    fontWeight: "600",
    fontSize: 13,
  },
  drawerLink: {
    paddingVertical: 10,
  },
  drawerLinkText: {
    fontSize: 14,
    fontWeight: "600",
    color: COLORS.textPrimary,
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
  previewOverlay: {
    flex: 1,
    backgroundColor: "rgba(255,248,238,0.85)",
    justifyContent: "center",
    alignItems: "center",
  },
previewClose: {
    position: "absolute",
    top: 54,
    left: 16,
    zIndex: 10,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: COLORS.card,
    borderWidth: 2,
    borderColor: COLORS.ink,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: COLORS.ink,
    shadowOffset: { width: 2, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 4,
  },
  uploadFallbackText: {
    color: COLORS.textMuted,
    fontSize: 13,
  },

  uploadMeta: {
    marginTop: 6,
    color: COLORS.textMuted,
    fontSize: 11,
  },

  /* Upload edit / delete */
  uploadMenuBtn: {
    position: "absolute",
    top: 54,
    left: 16,
    zIndex: 10,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: COLORS.card,
    borderWidth: 2,
    borderColor: COLORS.ink,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: COLORS.ink,
    shadowOffset: { width: 2, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 4,
  },
  previewMenu: {
    position: "absolute",
    top: 54,
    right: 16,
    zIndex: 10,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: COLORS.card,
    borderWidth: 2,
    borderColor: COLORS.ink,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: COLORS.ink,
    shadowOffset: { width: 2, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 4,
  },
  previewContent: {
    alignItems: "center",
    justifyContent: "center",
  },
  previewMedia: {},
  previewVideoFallback: {
    width: "100%",
    aspectRatio: 16 / 9,
    backgroundColor: COLORS.cream,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: 8,
  },
  previewVideoText: {
    color: COLORS.textMuted,
    fontSize: 14,
  },
  previewCaption: {
    color: COLORS.textPrimary,
    fontSize: 14,
    marginTop: 12,
    textAlign: "center",
    paddingHorizontal: 24,
    lineHeight: 20,
  },
  previewEditWrap: {
    paddingHorizontal: 24,
    marginTop: 12,
  },
  previewEditInput: {
    backgroundColor: COLORS.cream,
    color: COLORS.textPrimary,
    borderRadius: 10,
    padding: 12,
    fontSize: 14,
    minHeight: 60,
    textAlignVertical: "top",
    borderWidth: 1.5,
    borderColor: COLORS.peach,
  },
  previewEditBtns: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 16,
    marginTop: 8,
  },
  previewOptionsCard: {
    position: "absolute",
    top: 92,
    right: 16,
    backgroundColor: COLORS.card,
    borderRadius: 12,
    paddingVertical: 4,
    minWidth: 160,
    borderWidth: 2,
    borderColor: COLORS.ink,
    shadowColor: COLORS.ink,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 8,
  },
  previewOption: {
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  previewOptionText: {
    color: COLORS.textPrimary,
    fontSize: 15,
    fontWeight: "500",
    textAlign: "center",
  },
  previewOptionDivider: {
    height: 1,
    backgroundColor: COLORS.divider,
    marginHorizontal: 8,
  },
});
