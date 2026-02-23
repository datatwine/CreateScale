// src/components/SocialLoginButtons.js
//
// All 3 social providers in one file. The mobile app sends raw
// auth codes (or Google ID tokens) to POST /api/auth/oauth/
// and gets back a DRF Token. No secrets ever touch the app.

import React, { useContext, useState, useEffect } from "react";
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Alert,
} from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as AuthSession from "expo-auth-session";
import * as Google from "expo-auth-session/providers/google";
import { AuthContext } from "../context/AuthContext";
import { API_BASE_URL } from "../config/api";

// Required for Expo auth session to dismiss the browser
WebBrowser.maybeCompleteAuthSession();

// ─── OAuth Discovery Endpoints ──────────────────────────────────
const twitterDiscovery = {
    authorizationEndpoint: "https://twitter.com/i/oauth2/authorize",
    tokenEndpoint: "https://api.twitter.com/2/oauth2/token",
};

const linkedinDiscovery = {
    authorizationEndpoint: "https://www.linkedin.com/oauth/v2/authorization",
    tokenEndpoint: "https://www.linkedin.com/oauth/v2/accessToken",
};

// ─── Config ─────────────────────────────────────────────────────
// In Expo Go, the Web Client ID works for all platforms via Expo's proxy.
// If you build standalone (eas build), use platform-specific client IDs.
const GOOGLE_WEB_CLIENT_ID =
    "404648158729-449idoik2u1ko42ohcu7vnofrft31cmc.apps.googleusercontent.com";
const TWITTER_CLIENT_ID = "NWVvcmdFYlN1b3ItMmJjcVdUWHc6MTpjaQ";
const LINKEDIN_CLIENT_ID = "86ochmsy8bk9pu";

export default function SocialLoginButtons() {
    const { loginWithToken } = useContext(AuthContext);
    const [loading, setLoading] = useState("");

    // ── Google (uses Expo's built-in provider) ──────────────────
    const [googleRequest, googleResponse, googlePromptAsync] =
        Google.useIdTokenAuthRequest({
            clientId: GOOGLE_WEB_CLIENT_ID,
        });

    useEffect(() => {
        if (googleResponse?.type === "success") {
            const idToken = googleResponse.params.id_token;
            handleBackendAuth("google", { token: idToken });
        }
    }, [googleResponse]);

    // ── Twitter (PKCE auth code flow) ─────────────────────────
    const twitterRedirectUri = AuthSession.makeRedirectUri({ scheme: "createscaleapp" });
    const [twitterRequest, twitterResponse, twitterPromptAsync] =
        AuthSession.useAuthRequest(
            {
                clientId: TWITTER_CLIENT_ID,
                redirectUri: twitterRedirectUri,
                scopes: ["tweet.read", "users.read", "offline.access"],
                usePKCE: true,
                responseType: AuthSession.ResponseType.Code,
            },
            twitterDiscovery
        );

    useEffect(() => {
        if (twitterResponse?.type === "success" && twitterRequest) {
            handleBackendAuth("twitter", {
                code: twitterResponse.params.code,
                redirect_uri: twitterRedirectUri,
                code_verifier: twitterRequest.codeVerifier,
            });
        }
    }, [twitterResponse]);

    // ── LinkedIn (auth code flow, no PKCE) ────────────────────
    const linkedinRedirectUri = AuthSession.makeRedirectUri({ scheme: "createscaleapp" });
    const [linkedinRequest, linkedinResponse, linkedinPromptAsync] =
        AuthSession.useAuthRequest(
            {
                clientId: LINKEDIN_CLIENT_ID,
                redirectUri: linkedinRedirectUri,
                scopes: ["openid", "profile", "email"],
                responseType: AuthSession.ResponseType.Code,
            },
            linkedinDiscovery
        );

    useEffect(() => {
        if (linkedinResponse?.type === "success") {
            handleBackendAuth("linkedin", {
                code: linkedinResponse.params.code,
                redirect_uri: linkedinRedirectUri,
            });
        }
    }, [linkedinResponse]);

    // ── Shared: send code/token to backend, get DRF token ─────
    async function handleBackendAuth(provider, payload) {
        setLoading(provider);
        try {
            const response = await fetch(`${API_BASE_URL}/auth/oauth/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider, ...payload }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || `${provider} login failed`);
            }
            await loginWithToken(data.token);
        } catch (err) {
            Alert.alert("Login Failed", err.message);
        } finally {
            setLoading("");
        }
    }

    return (
        <View style={styles.container}>
            <Text style={styles.dividerText}>or continue with</Text>
            <View style={styles.row}>
                <TouchableOpacity
                    style={[styles.button, { backgroundColor: "#4285F4" }]}
                    onPress={() => googlePromptAsync()}
                    disabled={!googleRequest || loading === "google"}
                >
                    <Text style={styles.buttonText}>
                        {loading === "google" ? "..." : "Google"}
                    </Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.button, { backgroundColor: "#1DA1F2" }]}
                    onPress={() => twitterPromptAsync()}
                    disabled={!twitterRequest || loading === "twitter"}
                >
                    <Text style={styles.buttonText}>
                        {loading === "twitter" ? "..." : "Twitter"}
                    </Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.button, { backgroundColor: "#0077B5" }]}
                    onPress={() => linkedinPromptAsync()}
                    disabled={!linkedinRequest || loading === "linkedin"}
                >
                    <Text style={styles.buttonText}>
                        {loading === "linkedin" ? "..." : "LinkedIn"}
                    </Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        marginTop: 16,
    },
    dividerText: {
        color: "#999",
        fontSize: 13,
        textAlign: "center",
        marginBottom: 12,
    },
    row: {
        flexDirection: "row",
        gap: 8,
    },
    button: {
        flex: 1,
        borderRadius: 10,
        paddingVertical: 10,
        alignItems: "center",
        justifyContent: "center",
    },
    buttonText: {
        color: "#fff",
        fontWeight: "600",
        fontSize: 13,
    },
});
