from rest_framework.throttling import AnonRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    # A dedicated scope so auth endpoints share their own per-IP budget,
    # instead of colliding with the global AnonRateThrottle cache key.
    scope = "auth"
    rate = "5/minute"
