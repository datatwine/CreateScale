// src/components/MediaViewer.js
//
// Full-screen viewer for a single upload — images (expo-image) and videos
// (expo-video, with native playback controls). Reused by:
//   - ProfileScreen        → own profile, passes onEdit/onDelete (caption edit
//                            + delete surface in the ••• menu)
//   - ProfileDetailScreen  → another user's profile, read-only (no menu)
//
// The caller passes a pre-resolved `media` object ({ uri, isVideo, caption,
// id }); this component never resolves relative URLs itself. Build it with
// buildMediaSource from ../utils/mediaViewer.

import React, { useEffect, useState } from "react";
import {
    Modal,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useVideoPlayer, VideoView } from "expo-video";
import { COLORS } from "../config/theme";

export default function MediaViewer({ visible, media, onClose, onEdit, onDelete }) {
    const insets = useSafeAreaInsets();
    const [showOptions, setShowOptions] = useState(false);
    const [editing, setEditing] = useState(false);
    const [editCaption, setEditCaption] = useState("");

    // Hooks must run unconditionally, so the player is always created (source
    // is null for images) and the early return below sits *after* every hook.
    const isVideo = !!media?.isVideo;
    const player = useVideoPlayer(isVideo ? media.uri : null, (p) => {
        if (p) {
            p.loop = false;
            p.play();
        }
    });

    // Reset the transient menu/edit state whenever the shown media changes.
    useEffect(() => {
        setShowOptions(false);
        setEditing(false);
        setEditCaption(media?.caption || "");
    }, [media]);

    if (!visible || !media) return null;

    const canManage = !!(onEdit || onDelete);

    const handleSaveCaption = () => {
        setEditing(false);
        setShowOptions(false);
        onEdit?.(media.id, editCaption);
    };

    return (
        <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
            <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={onClose}>
                <TouchableOpacity
                    activeOpacity={1}
                    onPress={() => {}}
                    style={styles.mediaContainer}
                >
                    {isVideo ? (
                        <VideoView
                            player={player}
                            style={styles.video}
                            nativeControls
                            contentFit="contain"
                            allowsFullscreen
                        />
                    ) : (
                        <Image
                            source={{ uri: media.uri }}
                            style={styles.image}
                            contentFit="contain"
                        />
                    )}

                    {editing ? (
                        <View style={styles.editWrap}>
                            <TextInput
                                style={styles.editInput}
                                value={editCaption}
                                onChangeText={setEditCaption}
                                multiline
                                autoFocus
                                placeholder="Write a caption..."
                                placeholderTextColor={COLORS.placeholder}
                            />
                            <View style={styles.editBtns}>
                                <TouchableOpacity onPress={handleSaveCaption}>
                                    <Text style={styles.editSave}>Save</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    onPress={() => {
                                        setEditing(false);
                                        setEditCaption(media.caption || "");
                                    }}
                                >
                                    <Text style={styles.editCancel}>Cancel</Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    ) : editCaption ? (
                        <Text style={styles.caption}>{editCaption}</Text>
                    ) : null}
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.closeBtn, { top: insets.top + 16, left: 16 }]}
                    onPress={onClose}
                >
                    <Ionicons name="close" size={24} color={COLORS.ink} />
                </TouchableOpacity>

                {canManage && (
                    <TouchableOpacity
                        style={[styles.optionsBtn, { top: insets.top + 16, right: 16 }]}
                        onPress={() => setShowOptions((v) => !v)}
                    >
                        <Ionicons name="ellipsis-vertical" size={20} color={COLORS.ink} />
                    </TouchableOpacity>
                )}

                {canManage && showOptions && (
                    <View style={[styles.optionsCard, { top: insets.top + 60, right: 16 }]}>
                        {onEdit && (
                            <TouchableOpacity
                                style={styles.option}
                                onPress={() => {
                                    setShowOptions(false);
                                    setEditing(true);
                                }}
                            >
                                <Text style={styles.optionText}>Edit caption</Text>
                            </TouchableOpacity>
                        )}
                        {onEdit && onDelete && <View style={styles.optionDivider} />}
                        {onDelete && (
                            <TouchableOpacity
                                style={styles.option}
                                onPress={() => {
                                    setShowOptions(false);
                                    onDelete(media.id);
                                }}
                            >
                                <Text style={[styles.optionText, { color: COLORS.dangerBright }]}>
                                    Delete
                                </Text>
                            </TouchableOpacity>
                        )}
                    </View>
                )}
            </TouchableOpacity>
        </Modal>
    );
}

const styles = StyleSheet.create({
    backdrop: {
        flex: 1,
        backgroundColor: "rgba(0,0,0,0.95)",
        justifyContent: "center",
        alignItems: "center",
    },
    mediaContainer: {
        flex: 1,
        justifyContent: "center",
        alignItems: "center",
        width: "100%",
    },
    image: {
        width: "100%",
        height: "80%",
    },
    video: {
        width: "100%",
        height: "60%",
    },
    caption: {
        color: "#FFFFFF",
        fontSize: 14,
        textAlign: "center",
        marginTop: 12,
        paddingHorizontal: 24,
    },
    editWrap: {
        width: "100%",
        paddingHorizontal: 24,
        marginTop: 12,
    },
    editInput: {
        backgroundColor: COLORS.card,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: COLORS.ink,
        color: COLORS.textPrimary,
        paddingHorizontal: 12,
        paddingVertical: 8,
        fontSize: 14,
        minHeight: 44,
    },
    editBtns: {
        flexDirection: "row",
        justifyContent: "flex-end",
        gap: 20,
        marginTop: 8,
    },
    editSave: {
        color: COLORS.accent,
        fontWeight: "600",
        fontSize: 14,
    },
    editCancel: {
        color: COLORS.textMuted,
        fontSize: 14,
    },
    closeBtn: {
        position: "absolute",
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: COLORS.card,
        borderWidth: 2,
        borderColor: COLORS.ink,
        alignItems: "center",
        justifyContent: "center",
        elevation: 4,
    },
    optionsBtn: {
        position: "absolute",
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: COLORS.card,
        borderWidth: 2,
        borderColor: COLORS.ink,
        alignItems: "center",
        justifyContent: "center",
        elevation: 4,
    },
    optionsCard: {
        position: "absolute",
        backgroundColor: COLORS.card,
        borderRadius: 12,
        paddingVertical: 4,
        minWidth: 160,
        borderWidth: 2,
        borderColor: COLORS.ink,
        elevation: 8,
    },
    option: {
        paddingVertical: 12,
        paddingHorizontal: 16,
        alignItems: "center",
    },
    optionText: {
        color: COLORS.textPrimary,
        fontSize: 15,
        fontWeight: "500",
    },
    optionDivider: {
        height: 1,
        backgroundColor: COLORS.divider,
        marginHorizontal: 8,
    },
});
