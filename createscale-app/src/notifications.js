// src/notifications.js
//
// Push notification setup for the Expo app. Two independent responsibilities,
// on purpose kept as separate functions with different call-once semantics:
//
// registerForPushNotifications(authToken) — permission + token + register
// with Django. Call on every login (the token can change across app
// reinstalls, so re-sending it on each login keeps Django current).
//
// setupNotificationResponseHandling(navigationRef) — tap handling. Call ONCE
// on app mount, decoupled from login/logout, and use the returned cleanup
// function in a useEffect teardown. If this were tied to login instead,
// each re-login would attach another live listener on top of the last one,
// and a single tap would fire navigate() once per accumulated listener.
//
// Works in Expo Go on a physical device. Does NOT work on iOS Simulator.
// For manual testing without Django, use Expo's web tool: expo.dev/notifications

import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import Constants from "expo-constants";
import { API_BASE_URL } from "./config/api";

// --- Configure how notifications behave when the app is already open ---
// Without this, notifications that arrive while the app is in the foreground
// silently disappear on iOS. This tells Expo: "show them anyway."
// shouldShowBanner/shouldShowList replace the deprecated shouldShowAlert as
// of expo-notifications ~0.32 (the version this app is pinned to).
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/**
 * Read the tap-to-navigate payload off a notification response and, if it
 * names a screen, navigate there. Shared by both the live listener and the
 * cold-start check below so they agree on the same data.screen contract.
 */
function _navigateFromResponse(response, navigationRef) {
  const data = response?.notification?.request?.content?.data;
  if (data?.screen && navigationRef?.current) {
    navigationRef.current.navigate(data.screen, { id: data.id });
  }
}

/**
 * Register this device for push notifications.
 *
 * Call this on every login (once you have the auth token). It:
 * 1. Asks the user for notification permission (shows the OS popup)
 * 2. Gets the push token (delivery address) from Expo
 * 3. Sends it to Django so Django can reach this phone later
 * 4. Sets up the Android notification channel (Android only)
 *
 * @param {string} authToken - The user's API auth token (for the Authorization header)
 */
export async function registerForPushNotifications(authToken) {
  // Whole body guarded: this is called fire-and-forget (no .catch()) from
  // App.js, so any unguarded throw here becomes an unhandled promise
  // rejection. getExpoPushTokenAsync() in particular throws in EAS/standalone
  // builds when extra.eas.projectId is missing from app config — Expo Go
  // supplies ambient project context, so this only surfaces outside it.
  try {
    const { status } = await Notifications.requestPermissionsAsync();

    // User said no — respect it. We can't send them notifications.
    if (status !== "granted") {
      return;
    }

    // The token looks like: ExponentPushToken[abc123...]
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
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

    // Android requires a "channel" for notifications (iOS ignores this).
    // Without it, notifications may not show on some Android devices.
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Default",
        importance: Notifications.AndroidImportance.HIGH,
        sound: "default",
      });
    }
  } catch (err) {
    console.warn("Push notification registration failed:", err);
  }
}

/**
 * Set up notification-tap handling. Call ONCE on app mount (NOT tied to
 * login) and pass the returned cleanup function to your useEffect's
 * teardown. Handles two cases:
 *
 * 1. Live tap — the app is running or backgrounded when the user taps.
 * 2. Cold-start tap — the tap is what LAUNCHED the app from fully-killed
 *    state. The live listener can't see this: it wasn't attached yet when
 *    the tap happened. getLastNotificationResponseAsync() is Expo's way of
 *    asking "was this app just launched by a notification tap?" — checked
 *    once here, on mount.
 *
 * Both the cold-start check and the live listener can end up handling the
 * SAME launch tap (SDK/timing dependent), which would otherwise navigate
 * twice for one tap — deduped here by notification.request.identifier.
 *
 * @param {object} navigationRef - React Navigation ref, so we can navigate on tap
 * @returns {Function} cleanup function — call on unmount to remove the listener
 */
export function setupNotificationResponseHandling(navigationRef) {
  let lastHandledId = null;

  const handle = (response) => {
    const id = response?.notification?.request?.identifier;
    if (id && id === lastHandledId) {
      return;
    }
    if (id) {
      lastHandledId = id;
    }
    _navigateFromResponse(response, navigationRef);
  };

  Notifications.getLastNotificationResponseAsync().then((response) => {
    if (response) {
      handle(response);
    }
  });

  const subscription =
    Notifications.addNotificationResponseReceivedListener(handle);

  return () => subscription.remove();
}
