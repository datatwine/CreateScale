"""Authenticated Razorpay SDK client factory.

Centralizing client construction means:
  - Credentials are read once (from settings, populated by env vars).
  - Tests can monkeypatch this single function to mock the entire SDK.
  - We fail loudly if credentials are missing rather than silently 401-ing
    against Razorpay's API.

Why the import is lazy: the razorpay-python SDK can fail to import on some
Python/setuptools combinations (e.g. it uses pkg_resources, removed from
setuptools 70+). By importing inside the function we keep the booking
views, dashboards, and admin functional even if Razorpay isn't usable —
only the actual payment paths break, with a clean error message.
"""

from django.conf import settings


def get_client():
    """Return an authenticated Razorpay Client. Raises if creds are missing."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RuntimeError(
            "Razorpay is not configured. Set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET in the environment."
        )
    import razorpay  # lazy — see module docstring

    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
