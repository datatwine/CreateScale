import React, { useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import * as Location from "expo-location";
import { Ionicons } from "@expo/vector-icons";
import { COLORS } from "../config/theme";
import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";
import PressableStamp from "../components/PressableStamp";

async function shrinkImage(uri, maxWidth) {
  const out = await ImageManipulator.manipulateAsync(
    uri,
    [{ resize: { width: maxWidth } }],
    { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG }
  );
  return out.uri;
}

export default function EditProfileScreen() {
  const navigation = useNavigation();
  const { token, logout } = useContext(AuthContext);

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [updatingPicture, setUpdatingPicture] = useState(false);

  const [bio, setBio] = useState("");
  const [profession, setProfession] = useState("");
  const [location, setLocation] = useState("");
  const [isPerformer, setIsPerformer] = useState(false);
  const [isPotentialClient, setIsPotentialClient] = useState(false);

  const initial = useRef({}).current;

  const avatarUrl = profile
    ? profile?.profile_picture_url || profile?.profile_picture || null
    : null;

  const makeMediaUrl = (pathOrUrl) => {
    if (!pathOrUrl) return null;
    if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
      return pathOrUrl;
    }
    const backendRoot = API_BASE_URL.replace(/\/api\/?$/, "");
    if (pathOrUrl.startsWith("/")) return backendRoot + pathOrUrl;
    return `${backendRoot}/${pathOrUrl}`;
  };

  const loadProfile = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/users/me/`, {
        method: "GET",
        headers: { Authorization: `Token ${token}`, Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Failed to load profile");
      const data = await response.json();
      setProfile(data);
      setBio(data.bio || "");
      setProfession(data.profession || "");
      setLocation(data.location || "");
      setIsPerformer(Boolean(data.is_performer));
      setIsPotentialClient(Boolean(data.is_potential_client));
      initial.bio = data.bio || "";
      initial.profession = data.profession || "";
      initial.location = data.location || "";
      initial.isPerformer = Boolean(data.is_performer);
      initial.isPotentialClient = Boolean(data.is_potential_client);
    } catch (err) {
      console.error("Error loading profile", err);
      Alert.alert("Error", "Could not load profile.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleSave = async () => {
    if (!token || !profile) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/users/me/`, {
        method: "PATCH",
        headers: {
          Authorization: `Token ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          bio, profession, location,
          is_performer: isPerformer,
          is_potential_client: isPotentialClient,
        }),
      });
      if (!response.ok) throw new Error("Failed to save");
      const updated = await response.json();
      setProfile(updated);
      Alert.alert("Saved", "Your profile has been updated.");
      navigation.goBack();
    } catch (err) {
      console.error("Error saving profile", err);
      Alert.alert("Error", "Could not save changes.");
    } finally {
      setSaving(false);
    }
  };

  const hasChanges =
    bio !== initial.bio ||
    profession !== initial.profession ||
    location !== initial.location ||
    isPerformer !== initial.isPerformer ||
    isPotentialClient !== initial.isPotentialClient;

  const handlePickProfilePicture = async () => {
    if (!token) return;
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "We need access to your photos.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });
    if (result.canceled) return;
    const asset = result.assets?.[0];
    if (!asset) return;

    let avatarUri = asset.uri;
    try {
      avatarUri = await shrinkImage(asset.uri, 512);
    } catch (e) {
      console.warn("avatar shrink failed", e);
    }

    const formData = new FormData();
    formData.append("profile_picture", {
      uri: avatarUri,
      name: "profile.jpg",
      type: "image/jpeg",
    });

    setUpdatingPicture(true);
    try {
      const response = await fetch(`${API_BASE_URL}/users/me/`, {
        method: "PATCH",
        headers: { Authorization: `Token ${token}`, Accept: "application/json" },
        body: formData,
      });
      if (!response.ok) throw new Error("Failed to update picture");
      const updated = await response.json();
      setProfile(updated);
      Alert.alert("Updated", "Profile picture changed.");
    } catch (err) {
      console.error("Error updating picture", err);
      Alert.alert("Error", "Could not update picture.");
    } finally {
      setUpdatingPicture(false);
    }
  };

  const handleDetectLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        Alert.alert("Permission needed", "We need location access.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({});
      const places = await Location.reverseGeocodeAsync(position.coords);
      const place = places[0];
      const city = place.city || place.subregion || place.region || "";
      const country = place.country || "";
      const formatted = [city, country].filter(Boolean).join(", ");
      if (!formatted) {
        Alert.alert("Couldn't detect", "Please type your city manually.");
        return;
      }
      setLocation(formatted);
    } catch (err) {
      console.error("Location detection error", err);
      Alert.alert("Error", "Could not detect location.");
    }
  };

  if (!token) {
    return (
      <View style={styles.loadingFullScreen}>
        <ActivityIndicator size="large" color={COLORS.accent} />
      </View>
    );
  }

  if (loading) {
    return (
      <View style={styles.loadingFullScreen}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={styles.loadingText}>Loading profile…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={["top"]}>
      <View style={{ flex: 1, backgroundColor: COLORS.background }}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Edit Profile</Text>
        <PressableStamp
          onPress={handleSave}
          disabled={!hasChanges || saving}
          stampOffset={3}
          borderRadius={12}
          borderColor={COLORS.ink}
          borderWidth={2}
          style={{ paddingHorizontal: 16, paddingVertical: 6 }}
        >
          <Text style={[styles.saveButton, !hasChanges && { opacity: 0.4 }]}>{saving ? "Saving…" : "Save"}</Text>
        </PressableStamp>
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent}>
        <TouchableOpacity onPress={handlePickProfilePicture} style={styles.picContainer}>
          <View style={styles.picCircle}>
            {avatarUrl ? (
              <Image source={{ uri: makeMediaUrl(avatarUrl) }} style={styles.picImage} />
            ) : (
              <Text style={styles.picInitial}>
                {(profile?.username || "U").charAt(0).toUpperCase()}
              </Text>
            )}
          </View>
          <Text style={styles.picHint}>
            {updatingPicture ? "Updating…" : "Tap to change picture"}
          </Text>
        </TouchableOpacity>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>BIO</Text>
          <TextInput
            style={styles.input}
            placeholder="Add a bio"
            placeholderTextColor={COLORS.textMuted}
            multiline
            value={bio}
            onChangeText={setBio}
          />
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>LOCATION</Text>
            <TouchableOpacity onPress={handleDetectLocation}>
              <Text style={styles.linkText}>Use my location</Text>
            </TouchableOpacity>
          </View>
          <TextInput
            style={styles.input}
            placeholder="City, Country"
            placeholderTextColor={COLORS.textMuted}
            value={location}
            onChangeText={setLocation}
          />
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>PROFESSION</Text>
          <TextInput
            style={styles.input}
            placeholder="What do you do?"
            placeholderTextColor={COLORS.textMuted}
            value={profession}
            onChangeText={setProfession}
          />
        </View>

        <View style={styles.toggleRow}>
          <TouchableOpacity
            style={[styles.togglePill, isPotentialClient && styles.togglePillActive]}
            onPress={() => setIsPotentialClient((p) => !p)}
          >
            <Text style={[styles.toggleText, isPotentialClient && styles.toggleTextActive]}>
              Potential client
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.togglePill, isPerformer && styles.togglePillActive]}
            onPress={() => setIsPerformer((p) => !p)}
          >
            <Text style={[styles.toggleText, isPerformer && styles.toggleTextActive]}>
              Performer
            </Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={styles.logoutButton} onPress={logout}>
          <Text style={styles.logoutText}>Log out</Text>
        </TouchableOpacity>
      </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#000",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: COLORS.textPrimary,
  },
  saveButton: {
    fontSize: 16,
    fontWeight: "600",
    color: COLORS.accent,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 40,
  },
  picContainer: {
    alignItems: "center",
    marginVertical: 24,
  },
  picCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 3,
    borderColor: COLORS.accent,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.cream,
    overflow: "hidden",
  },
  picImage: {
    width: "100%",
    height: "100%",
    resizeMode: "cover",
  },
  picInitial: {
    fontSize: 32,
    fontWeight: "700",
    color: COLORS.accent,
  },
  picHint: {
    marginTop: 8,
    fontSize: 13,
    color: COLORS.textSecondary,
  },
  section: {
    marginTop: 20,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: "600",
    color: COLORS.textSecondary,
    letterSpacing: 1.1,
    marginBottom: 6,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  input: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: COLORS.card,
    borderWidth: 2,
    borderColor: COLORS.ink,
    color: COLORS.textPrimary,
    fontSize: 14,
    textAlignVertical: "top",
    minHeight: 44,
  },
  linkText: {
    color: COLORS.accent,
    fontSize: 13,
    fontWeight: "500",
  },
  toggleRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 24,
  },
  togglePill: {
    flex: 1,
    borderRadius: 999,
    borderWidth: 2,
    borderColor: COLORS.ink,
    paddingVertical: 10,
    alignItems: "center",
    backgroundColor: COLORS.card,
  },
  togglePillActive: {
    backgroundColor: COLORS.accent,
    borderColor: COLORS.ink,
  },
  toggleText: {
    fontSize: 13,
    color: COLORS.textPrimary,
    fontWeight: "500",
  },
  toggleTextActive: {
    color: COLORS.card,
  },
  logoutButton: {
    marginTop: 32,
    marginBottom: 16,
    borderRadius: 999,
    borderWidth: 2,
    borderColor: "#FF3B30",
    backgroundColor: COLORS.card,
    paddingVertical: 12,
    alignItems: "center",
  },
  logoutText: {
    color: "#FF3B30",
    fontSize: 14,
    fontWeight: "600",
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
});
