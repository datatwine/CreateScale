import React, { useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
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
import { SafeAreaView } from "react-native-safe-area-context";
import { useNavigation, useFocusEffect } from "@react-navigation/native";
import * as ImageManipulator from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";
import { Ionicons } from "@expo/vector-icons";
import { COLORS } from "../config/theme";
import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";
import { uploadMedia } from "../api/upload";
import PressableStamp from "../components/PressableStamp";

async function shrinkImage(uri, maxWidth) {
  const out = await ImageManipulator.manipulateAsync(
    uri,
    [{ resize: { width: maxWidth } }],
    { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG }
  );
  return out.uri;
}

let VideoCompressor = null;
try {
  VideoCompressor = require("react-native-compressor").Video;
} catch {}

async function compressVideo(uri) {
  return await VideoCompressor.compress(
    uri,
    {
      compressionMethod: "manual",
      maxSize: 1920,           // longest side cap (1080p target)
      bitrate: 4_000_000,      // 4 Mbps — strong quality for social video
    },
    // Progress callback (0..1). No-op for now; could drive a progress bar
    // by lifting state into the component if desired.
    () => {}
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
    backgroundColor = "#EDFBEE";
    textColor = "#1a7f2e";
  } else if (tone === "warning") {
    backgroundColor = "#F5F0FF";
    textColor = "#5B21B6";
  } else if (tone === "danger") {
    backgroundColor = "#FFE6E0";
    textColor = "#8f3400";
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
                placeholderTextColor="#666"
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
              <Text style={[styles.previewOptionText, { color: "#FF3B30" }]}>Delete</Text>
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
  const { token } = useContext(AuthContext);

  const [profile, setProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
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
      if (!response.ok) throw new Error("Failed to load profile");
      const data = await response.json();
      setProfile(data);
    } catch (err) {
      console.error("Error loading profile", err);
      if (!silent) Alert.alert("Error", "Could not load your profile.");
    } finally {
      setLoadingProfile(false);
    }
  }, [token]);

  const loadUploads = useCallback(async (silent = false) => {
    if (!token) return;
    if (!silent) setLoadingUploads(true);
    try {
      const response = await fetch(buildApiUrl("/users/me/uploads/"), {
        method: "GET",
        headers: { Authorization: `Token ${token}`, Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Failed to load uploads");
      const data = await response.json();
      setUploads(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error loading uploads", err);
    } finally {
      setLoadingUploads(false);
    }
  }, [token]);

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
      setNewUploadCaption("");
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
          <TouchableOpacity onPress={() => navigation.navigate("EditProfile")}>
            <Ionicons name="settings-outline" size={24} color={COLORS.textPrimary} />
          </TouchableOpacity>
        </View>

        <View style={styles.profileHeader}>
          <View style={styles.avatarCircle}>
            {avatarUrl ? (
              <Image source={{ uri: avatarUrl }} style={styles.avatarImage} />
            ) : (
              <Text style={styles.avatarInitial}>
                {(profile.username || "U").charAt(0).toUpperCase()}
              </Text>
            )}
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#000",
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
    color: "#fff",
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
