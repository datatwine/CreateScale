# users/notifications.py
#
# Central utility for sending push notifications via Expo's free Push API.
# Every notification trigger in the codebase calls send_push_notification().
#
# How it works:
# 1. Look up all push tokens (delivery addresses) for the target user.
# 2. Build one message per token (same notification to each of their devices).
# 3. POST them to Expo's API in a single batch request.
# 4. If Expo reports a token as dead (user uninstalled the app), delete it
#    from our database so we stop trying to reach a dead device.
#
# Expo's push API is free, requires no API key, and handles both iOS and
# Android. The push token itself (issued by Expo to the app) is the auth.
# Docs: https://docs.expo.dev/push-notifications/sending-notifications/

import logging
import requests

from users.models import PushToken

logger = logging.getLogger(__name__)

# Expo's free push notification endpoint. No signup or API key needed.
# Accepts up to 100 messages per request.
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def _clean_dead_tokens(messages, results):
    """
    Helper: check Expo's response for dead tokens and delete them.

    When a user uninstalls the app, Apple/Google tells Expo the token is dead.
    Expo returns "DeviceNotRegistered" for that token. We delete it so we stop
    trying to reach a phone that can't hear us.

    Used by both send_push_notification() (1:1) and
    broadcast_push_notification() (batch).
    """
    dead_tokens = []
    for msg, result in zip(messages, results):
        if result.get("status") == "error":
            error_type = result.get("details", {}).get("error")
            if error_type == "DeviceNotRegistered":
                dead_tokens.append(msg["to"])

    if dead_tokens:
        deleted, _ = PushToken.objects.filter(token__in=dead_tokens).delete()
        logger.info("Removed %d dead push token(s)", deleted)


def send_push_notification(user, title, body, data=None):
    """
    Send a push notification to every device a user has registered.

    Args:
        user:  Django User instance — who to notify.
        title: Notification title shown on the phone (e.g. "Booking confirmed!").
        body:  Notification body text (e.g. "Rajath accepted your request").
        data:  Optional dict — invisible payload the app reads when the user
               taps the notification. Use for navigation hints like:
               {"screen": "HireDetail", "id": 42}
               The app reads data.screen and navigates there.

    This function is fire-and-forget: if Expo is down or the network blips,
    the notification silently fails. That's fine — push notifications are
    best-effort by design (Apple and Google don't guarantee delivery either).
    """

    # Step 1: Look up all push tokens for this user.
    tokens = list(PushToken.objects.filter(user=user).values_list("token", flat=True))

    # No tokens = user never granted notification permission, or they
    # uninstalled the app on all devices. Nothing to do.
    if not tokens:
        return

    # Step 2: Build one message per device.
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "sound": "default",
            "data": data or {},
        }
        for token in tokens
    ]

    # Step 3: Send to Expo's API in one batch request.
    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
    except requests.RequestException:
        logger.warning("Failed to reach Expo push API for user %s", user.id)
        return

    # Step 4: Clean up dead tokens.
    if response.ok:
        _clean_dead_tokens(messages, response.json().get("data", []))


def broadcast_push_notification(title, body, data=None, exclude_user=None):
    """
    Send a push notification to ALL registered devices (broadcast).

    This is for events that every user should see — like a new live event
    appearing on the Live Events page. Unlike send_push_notification() which
    targets one user, this queries EVERY push token in the database.

    Args:
        title:        Notification title (e.g. "New live event!")
        body:         Notification body (e.g. "Rajath is performing at Wedding on Aug 15")
        data:         Optional dict for tap-to-navigate (e.g. {"screen": "LiveEvents"})
        exclude_user: Optional User instance to skip (e.g. the performer who just
                      accepted — they already know). Avoids a redundant notification.

    Because this can mean thousands of tokens, it sends in batches of 100
    (Expo's recommended limit per request). This function should be called
    from a Celery task, NOT from a request/response cycle — it blocks while
    it works through all batches.
    """

    # Step 1: Get ALL tokens. If exclude_user is set, skip their devices.
    qs = PushToken.objects.all()
    if exclude_user:
        qs = qs.exclude(user=exclude_user)
    tokens = list(qs.values_list("token", flat=True))

    if not tokens:
        return

    # Step 2: Split into chunks of 100. Expo accepts up to 100 messages per
    # request. Sending more than 100 may get rate-limited or rejected.
    BATCH_SIZE = 100

    for i in range(0, len(tokens), BATCH_SIZE):
        batch = tokens[i : i + BATCH_SIZE]

        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "sound": "default",
                "data": data or {},
            }
            for token in batch
        ]

        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        except requests.RequestException:
            logger.warning("Broadcast batch %d-%d failed (network)", i, i + len(batch))
            continue

        if response.ok:
            _clean_dead_tokens(messages, response.json().get("data", []))

    logger.info(
        "Broadcast complete: %d tokens in %d batches",
        len(tokens),
        (len(tokens) + BATCH_SIZE - 1) // BATCH_SIZE,
    )
