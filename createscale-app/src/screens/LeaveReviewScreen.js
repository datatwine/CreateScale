// src/screens/LeaveReviewScreen.js

import React, { useState, useContext } from "react";
import {
    View,
    Text,
    StyleSheet,
    TextInput,
    TouchableOpacity,
    ActivityIndicator,
    Alert,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { API_BASE_URL } from "../config/api";
import { AuthContext } from "../context/AuthContext";
import { COLORS } from "../config/theme";
import PressableStamp from "../components/PressableStamp";

export default function LeaveReviewScreen({ route, navigation }) {
    const { token } = useContext(AuthContext);
    
    // We expect the engagement ID to be passed as a route param
    const { engagementId, otherPartyName, occasion } = route.params || {};

    const [rating, setRating] = useState("");
    const [comment, setComment] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async () => {
        if (!rating) {
            Alert.alert("Missing Rating", "Please provide a score out of 10.");
            return;
        }

        const numericRating = parseInt(rating, 10);
        if (isNaN(numericRating) || numericRating < 0 || numericRating > 10) {
            Alert.alert("Invalid Rating", "Score must be a number between 0 and 10.");
            return;
        }



        setLoading(true);
        try {
            const url = `${API_BASE_URL.replace(/\/+$/, "")}/bookings/engagements/${engagementId}/review/`;
            const res = await fetch(url, {
                method: "POST",
                headers: {
                    Authorization: `Token ${token}`,
                    "Content-Type": "application/json",
                    Accept: "application/json",
                },
                body: JSON.stringify({
                    rating: numericRating,
                    comment: comment.trim(),
                }),
            });

            const data = await res.json().catch(() => ({}));

            if (res.ok) {
                Alert.alert("Success", "Your review has been submitted!");
                // Go back to the previous screen
                navigation.goBack();
            } else {
                Alert.alert("Error", data.detail || "Failed to submit review.");
            }
        } catch (err) {
            console.error("Submit review error:", err);
            Alert.alert("Error", "Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <SafeAreaView style={styles.safeArea} edges={["top"]}>
            <KeyboardAvoidingView 
                style={styles.keyboardAvoid} 
                behavior={Platform.OS === "ios" ? "padding" : "height"}
            >
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                        <Ionicons name="arrow-back" size={24} color={COLORS.textPrimary} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Leave a Review</Text>
                    <View style={styles.backButtonPlaceholder} />
                </View>

                <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
                    <Text style={styles.subtitle}>
                        How was your experience with <Text style={styles.bold}>{otherPartyName}</Text> at the <Text style={styles.bold}>{occasion}</Text>?
                    </Text>

                    <View style={styles.card}>
                        <Text style={styles.label}>Score (0-10)</Text>
                        <TextInput
                            style={styles.ratingInput}
                            placeholder="10"
                            placeholderTextColor={COLORS.textMuted}
                            keyboardType="number-pad"
                            maxLength={2}
                            value={rating}
                            onChangeText={setRating}
                        />
                        <Text style={styles.helpText}>10 is excellent, 0 is terrible.</Text>

                        <Text style={[styles.label, { marginTop: 24 }]}>Comment</Text>
                        <TextInput
                            style={styles.commentInput}
                            placeholder="Write your review here..."
                            placeholderTextColor={COLORS.textMuted}
                            multiline
                            value={comment}
                            onChangeText={setComment}
                        />
                        
                        <View style={styles.buttonContainer}>
                            <PressableStamp
                                stampOffset={4}
                                stampOffsetY={4}
                                borderRadius={12}
                                borderColor={COLORS.ink}
                                borderWidth={2}
                                onPress={handleSubmit}
                                disabled={loading}
                                style={styles.submitButton}
                            >
                                {loading ? (
                                    <ActivityIndicator color={COLORS.white} />
                                ) : (
                                    <Text style={styles.submitButtonText}>Submit Review</Text>
                                )}
                            </PressableStamp>
                        </View>
                    </View>
                </ScrollView>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    safeArea: {
        flex: 1,
        backgroundColor: COLORS.background,
    },
    keyboardAvoid: {
        flex: 1,
    },
    header: {
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: COLORS.divider,
    },
    backButton: {
        padding: 4,
    },
    backButtonPlaceholder: {
        width: 32,
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: "700",
        color: COLORS.textPrimary,
    },
    scrollContent: {
        padding: 16,
    },
    subtitle: {
        fontSize: 16,
        color: COLORS.textSecondary,
        marginBottom: 24,
        lineHeight: 24,
    },
    bold: {
        fontWeight: "700",
        color: COLORS.textPrimary,
    },
    card: {
        backgroundColor: COLORS.card,
        borderRadius: 16,
        padding: 24,
        borderWidth: 1,
        borderColor: COLORS.divider,
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.05,
        shadowRadius: 12,
        elevation: 3,
    },
    label: {
        fontSize: 14,
        fontWeight: "600",
        color: COLORS.textPrimary,
        marginBottom: 8,
    },
    ratingInput: {
        backgroundColor: COLORS.cream,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: COLORS.ink,
        paddingHorizontal: 16,
        paddingVertical: 12,
        fontSize: 20,
        fontWeight: "600",
        color: COLORS.textPrimary,
        width: 80,
        textAlign: "center",
    },
    helpText: {
        fontSize: 12,
        color: COLORS.textMuted,
        marginTop: 6,
    },
    commentInput: {
        backgroundColor: COLORS.cream,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: COLORS.ink,
        paddingHorizontal: 16,
        paddingVertical: 12,
        fontSize: 15,
        color: COLORS.textPrimary,
        minHeight: 120,
        textAlignVertical: "top",
    },
    buttonContainer: {
        marginTop: 32,
    },
    submitButton: {
        backgroundColor: COLORS.successButton,
        paddingVertical: 14,
        alignItems: "center",
        justifyContent: "center",
    },
    submitButtonText: {
        color: COLORS.white,
        fontSize: 16,
        fontWeight: "700",
    },
});
