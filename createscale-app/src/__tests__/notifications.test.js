/**
 * TDD — written BEFORE implementation (issue #81, FILE 7).
 *
 * registerForPushNotifications() is the one entry point the app calls on
 * startup once the user is logged in. It must:
 *  - bail quietly if the user denies the permission popup
 *  - fetch the Expo push token and register it with Django
 *  - never throw if the network call fails (best-effort, like the backend)
 *  - navigate via navigationRef when a notification is tapped
 *  - set up an Android notification channel on Android only
 *
 * Run: npm test -- notifications
 */

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  addNotificationResponseReceivedListener: jest.fn(),
  setNotificationChannelAsync: jest.fn(),
  AndroidImportance: { HIGH: 4 },
}));

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import { registerForPushNotifications } from "../notifications";

const mockRequestPermissionsAsync = Notifications.requestPermissionsAsync;
const mockGetExpoPushTokenAsync = Notifications.getExpoPushTokenAsync;
const mockAddNotificationResponseReceivedListener =
  Notifications.addNotificationResponseReceivedListener;
const mockSetNotificationChannelAsync = Notifications.setNotificationChannelAsync;

describe("registerForPushNotifications", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn().mockResolvedValue({ ok: true });
    Platform.OS = "ios";
  });

  test("does nothing further when permission is denied", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "denied" });

    await registerForPushNotifications("auth-tok-123", { current: null });

    expect(mockGetExpoPushTokenAsync).not.toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("registers the token with Django when permission is granted", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123", { current: null });

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
      registerForPushNotifications("auth-tok-123", { current: null })
    ).resolves.not.toThrow();
  });

  test("navigates to the tapped notification's screen", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };

    await registerForPushNotifications("auth-tok-123", navigationRef);

    expect(mockAddNotificationResponseReceivedListener).toHaveBeenCalledTimes(1);
    const handler = mockAddNotificationResponseReceivedListener.mock.calls[0][0];

    handler({
      notification: {
        request: { content: { data: { screen: "BookingDetail", id: 42 } } },
      },
    });

    expect(navigate).toHaveBeenCalledWith("BookingDetail", { id: 42 });
  });

  test("does not navigate when the tapped notification has no screen", async () => {
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    const navigate = jest.fn();
    const navigationRef = { current: { navigate } };

    await registerForPushNotifications("auth-tok-123", navigationRef);

    const handler = mockAddNotificationResponseReceivedListener.mock.calls[0][0];
    handler({ notification: { request: { content: { data: {} } } } });

    expect(navigate).not.toHaveBeenCalled();
  });

  test("sets up an Android notification channel only on Android", async () => {
    Platform.OS = "android";
    mockRequestPermissionsAsync.mockResolvedValue({ status: "granted" });
    mockGetExpoPushTokenAsync.mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await registerForPushNotifications("auth-tok-123", { current: null });

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

    await registerForPushNotifications("auth-tok-123", { current: null });

    expect(mockSetNotificationChannelAsync).not.toHaveBeenCalled();
  });
});
