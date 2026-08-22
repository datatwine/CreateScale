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

import requests

# Seconds before any Razorpay gateway call gives up. Matches the RazorpayX
# client's _TIMEOUT in razorpayx.py. The pinned razorpay-python SDK (1.4.2)
# never sets a timeout on its own requests, so a hung upstream connection
# would otherwise block a Django worker indefinitely — both on user-facing
# requests (pay/verify/refund) and inside the Celery payout batch.
_GATEWAY_TIMEOUT = 30


class _TimedOutSession(requests.Session):
    """A requests.Session that defaults a timeout on every request.

    The SDK's Client calls session.<method>(url, auth=..., verify=..., **opts)
    and never passes a timeout. setdefault() injects ours while still letting
    an explicit timeout from a caller win.
    """

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", _GATEWAY_TIMEOUT)
        return super().request(method, url, **kwargs)


def get_client():
    """Return an authenticated Razorpay Client. Raises if creds are missing."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RuntimeError(
            "Razorpay is not configured. Set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET in the environment."
        )
    import razorpay  # lazy — see module docstring

    return razorpay.Client(
        session=_TimedOutSession(),
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
    )
