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

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { extra: { eas: { projectId: "test-project-id" } } } },
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

  test("passes an explicit projectId to getExpoPushTokenAsync", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123");

    expect(mockGetExpoPushTokenAsync).toHaveBeenCalledWith({
      projectId: "test-project-id",
    });
  });

  test("does not throw when getExpoPushTokenAsync itself throws", async () => {
    // Happens in EAS/standalone builds when extra.eas.projectId is missing —
    // must not become an unhandled rejection (this fn is called fire-and-forget).
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockRejectedValue(new Error("No projectId found"));

    await expect(
      registerForPushNotifications("auth-tok-123")
    ).resolves.not.toThrow();
    expect(global.fetch).not.toHaveBeenCalled();
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

  test("does not navigate twice when the same tap fires from both cold-start and the live listener", async () => {
    // Both getLastNotificationResponseAsync and the live listener can fire
    // for the same launch tap depending on SDK version/timing. They share a
    // notification.request.identifier when that happens — dedup on it.
    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };
    const sameResponse = {
      notification: {
        request: {
          identifier: "notif-abc-123",
          content: { data: { screen: "Bookings", id: 42 } },
        },
      },
    };
    mockGetLastNotificationResponseAsync.mockResolvedValue(sameResponse);

    setupNotificationResponseHandling(navigationRef);
    await Promise.resolve();
    await Promise.resolve();

    // Live listener fires for the SAME notification right after.
    const handler = mockAddNotificationResponseReceivedListener.mock.calls[0][0];
    handler(sameResponse);

    expect(navigate).toHaveBeenCalledTimes(1);
  });

  test("still navigates for a different notification after an earlier one", async () => {
    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };
    mockGetLastNotificationResponseAsync.mockResolvedValue({
      notification: {
        request: {
          identifier: "notif-first",
          content: { data: { screen: "Bookings", id: 1 } },
        },
      },
    });

    setupNotificationResponseHandling(navigationRef);
    await Promise.resolve();
    await Promise.resolve();

    const handler = mockAddNotificationResponseReceivedListener.mock.calls[0][0];
    handler({
      notification: {
        request: {
          identifier: "notif-second",
          content: { data: { screen: "LiveEvents", id: 2 } },
        },
      },
    });

    expect(navigate).toHaveBeenNthCalledWith(1, "Bookings", { id: 1 });
    expect(navigate).toHaveBeenNthCalledWith(2, "LiveEvents", { id: 2 });
  });
});
