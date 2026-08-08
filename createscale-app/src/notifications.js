// src/notifications.js
//
// Push notification setup for the Expo app.
// Three responsibilities:
// 1. Ask for permission + get the push token from Apple/Google (via Expo)
// 2. Send that token to our Django backend so it knows where to reach this phone
// 3. Handle what happens when the user taps a notification (navigate to the right screen)
//
// This module exports one function: registerForPushNotifications(token, navigationRef)
// Call it once on app startup, after the user is logged in.
//
// Works in Expo Go on a physical device. Does NOT work on iOS Simulator.
// For manual testing without Django, use Expo's web tool: expo.dev/notifications

import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { API_BASE_URL } from "./config/api";

// --- Configure how notifications behave when the app is already open ---
// Without this, notifications that arrive while the app is in the foreground
// silently disappear on iOS. This tells Expo: "show them anyway."
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/**
 * Register this device for push notifications.
 *
 * Call this once on app startup, after the user is logged in and you have
 * their auth token. It:
 * 1. Asks the user for notification permission (shows the OS popup)
 * 2. Gets the push token (delivery address) from Expo
 * 3. Sends it to Django so Django can reach this phone later
 * 4. Sets up a listener for when the user taps a notification
 *
 * @param {string} authToken - The user's API auth token (for the Authorization header)
 * @param {object} navigationRef - React Navigation ref, so we can navigate on tap
 */
export async function registerForPushNotifications(authToken, navigationRef) {
  const { status } = await Notifications.requestPermissionsAsync();

  // User said no — respect it. We can't send them notifications.
  if (status !== "granted") {
    return;
  }

  // The token looks like: ExponentPushToken[abc123...]
  const tokenData = await Notifications.getExpoPushTokenAsync();
  const pushToken = tokenData.data;

  // We send this on EVERY app launch (not just the first time) because the
  // token can change — app reinstall, OS update, etc. Django's update_or_create
  // handles duplicates gracefully.
  try {
    await fetch(`${API_BASE_URL}/users/push-token/`, {
      method: "POST",
      headers: {
        Authorization: `Token ${authToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token: pushToken }),
    });
  } catch (err) {
    // Network error — token didn't get registered this time.
    // It'll retry on next app launch. Not critical.
    console.warn("Failed to register push token:", err);
  }

  // When the user taps a notification, this listener fires. We read the
  // "data" payload Django sent (e.g. {screen: "BookingDetail", id: 42})
  // and navigate to the right screen.
  Notifications.addNotificationResponseReceivedListener((response) => {
    const data = response.notification.request.content.data;

    if (data?.screen && navigationRef?.current) {
      navigationRef.current.navigate(data.screen, { id: data.id });
    }
  });

  // Android requires a "channel" for notifications (iOS ignores this).
  // Without it, notifications may not show on some Android devices.
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "Default",
      importance: Notifications.AndroidImportance.HIGH,
      sound: "default",
    });
  }
}
