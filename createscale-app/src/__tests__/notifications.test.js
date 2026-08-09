/**
 * TDD — written BEFORE implementation (issue #81, FILE 7).
 *
 * registerForPushNotifications() handles permission + token + registering
 * with Django. Tap-handling is a SEPARATE function, setupNotificationResponseHandling():
 *  - registered once on app mount, decoupled from login, so re-login
 *    doesn't stack up duplicate listeners (each returns a cleanup fn)
 *  - checks getLastNotificationResponseAsync() once for a cold-start launch
 *    tap (a tap that launched the app from fully-killed state), since the
 *    live listener can't see a tap that happened before it was attached
 *
 * Run: npm test -- notifications
 */

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  addNotificationResponseReceivedListener: jest.fn(),
  getLastNotificationResponseAsync: jest.fn(),
  setNotificationChannelAsync: jest.fn(),
  AndroidImportance: { HIGH: 4 },
}));

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import {
  registerForPushNotifications,
  setupNotificationResponseHandling,
} from "../notifications";

const mockRequestPermissionsAsync = Notifications.requestPermissionsAsync;
const mockGetExpoPushTokenAsync = Notifications.getExpoPushTokenAsync;
const mockAddNotificationResponseReceivedListener =
  Notifications.addNotificationResponseReceivedListener;
const mockGetLastNotificationResponseAsync =
  Notifications.getLastNotificationResponseAsync;
const mockSetNotificationChannelAsync = Notifications.setNotificationChannelAsync;

describe("registerForPushNotifications", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn().mockResolvedValue({ ok: true });
    Platform.OS = "ios";
    mockGetLastNotificationResponseAsync.mockResolvedValue(null);
  });

  test("does nothing further when permission is denied", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "denied" });

    await registerForPushNotifications("auth-tok-123");

    expect(mockGetExpoPushTokenAsync).not.toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("registers the token with Django when permission is granted", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/users/push-token/",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Token auth-tok-123",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ token: "ExponentPushToken[abc123]" }),
      })
    );
  });

  test("does not throw when the registration request fails", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });
    global.fetch.mockRejectedValue(new Error("network down"));

    await expect(
      registerForPushNotifications("auth-tok-123")
    ).resolves.not.toThrow();
  });

  test("does not register a tap listener itself", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123");

    expect(mockAddNotificationResponseReceivedListener).not.toHaveBeenCalled();
  });

  test("sets up an Android notification channel only on Android", async () => {
    Platform.OS = "android";
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123");

    expect(mockSetNotificationChannelAsync).toHaveBeenCalledWith(
      "default",
      expect.objectContaining({ importance: 4 })
    );
  });

  test("skips the Android notification channel on iOS", async () => {
    Platform.OS = "ios";
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123");

    expect(mockSetNotificationChannelAsync).not.toHaveBeenCalled();
  });
});

describe("setupNotificationResponseHandling", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetLastNotificationResponseAsync.mockResolvedValue(null);
    mockAddNotificationResponseReceivedListener.mockReturnValue({
      remove: jest.fn(),
    });
  });

  test("navigates when a live notification is tapped", () => {
    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };

    setupNotificationResponseHandling(navigationRef);

    expect(mockAddNotificationResponseReceivedListener).toHaveBeenCalledTimes(1);
    const handler = mockAddNotificationResponseReceivedListener.mock.calls[0][0];

    handler({
      notification: {
        request: { content: { data: { screen: "Bookings", id: 42 } } },
      },
    });

    expect(navigate).toHaveBeenCalledWith("Bookings", { id: 42 });
  });

  test("does not navigate when the tapped notification has no screen", () => {
    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };

    setupNotificationResponseHandling(navigationRef);

    const handler = mockAddNotificationResponseReceivedListener.mock.calls[0][0];
    handler({ notification: { request: { content: { data: {} } } } });

    expect(navigate).not.toHaveBeenCalled();
  });

  test("returns a cleanup function that removes the listener", () => {
    const remove = jest.fn();
    mockAddNotificationResponseReceivedListener.mockReturnValue({ remove });
    const navigationRef = { current: { navigate: jest.fn() } };

    const cleanup = setupNotificationResponseHandling(navigationRef);
    cleanup();

    expect(remove).toHaveBeenCalledTimes(1);
  });

  test("navigates from a cold-start launch tap via getLastNotificationResponseAsync", async () => {
    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };
    mockGetLastNotificationResponseAsync.mockResolvedValue({
      notification: {
        request: { content: { data: { screen: "LiveEvents", id: 7 } } },
      },
    });

    setupNotificationResponseHandling(navigationRef);
    // getLastNotificationResponseAsync resolves asynchronously
    await Promise.resolve();
    await Promise.resolve();

    expect(navigate).toHaveBeenCalledWith("LiveEvents", { id: 7 });
  });

  test("cold-start check is a no-op when there was no launch notification", async () => {
    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };
    mockGetLastNotificationResponseAsync.mockResolvedValue(null);

    setupNotificationResponseHandling(navigationRef);
    await Promise.resolve();
    await Promise.resolve();

    expect(navigate).not.toHaveBeenCalled();
  });
});
