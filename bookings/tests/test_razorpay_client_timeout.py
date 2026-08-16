"""
Gateway Razorpay client timeout tests.

The pinned razorpay-python SDK (1.4.2) never sends a timeout on its HTTP
calls. We inject a default via a custom requests.Session in
bookings.services.razorpay_client. These tests pin that behavior: every
gateway request carries a timeout, an explicit one wins, and get_client()
wires the timed session into the SDK client.
"""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.test import override_settings

from bookings.services.razorpay_client import _GATEWAY_TIMEOUT, _TimedOutSession


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test_secret",
)
class TestRazorpayClientTimeout(SimpleTestCase):
    def test_session_applies_default_timeout(self):
        session = _TimedOutSession()
        with patch("requests.Session.request", return_value=Mock(status_code=200)) as m:
            session.post("https://api.razorpay.com/v1/orders", json={})

        self.assertEqual(m.call_count, 1)
        _, kwargs = m.call_args
        self.assertEqual(kwargs["timeout"], _GATEWAY_TIMEOUT)

    def test_explicit_timeout_not_overridden(self):
        session = _TimedOutSession()
        with patch("requests.Session.request", return_value=Mock(status_code=200)) as m:
            session.get("https://api.razorpay.com/v1/orders", timeout=5)

        self.assertEqual(m.call_count, 1)
        _, kwargs = m.call_args
        self.assertEqual(kwargs["timeout"], 5)

    def test_get_client_wires_timed_session(self):
        # Fake the lazily-imported SDK (not installed in this env) so we can
        # assert get_client() hands it a session that enforces the timeout.
        fake_sdk = Mock()
        fake_client = fake_sdk.Client.return_value
        with patch.dict(
            "sys.modules",
            {"razorpay": fake_sdk},
        ):
            from bookings.services.razorpay_client import get_client

            client = get_client()

        self.assertIs(client, fake_client)
        fake_sdk.Client.assert_called_once()
        _, kwargs = fake_sdk.Client.call_args
        self.assertIsInstance(kwargs["session"], _TimedOutSession)
        self.assertEqual(kwargs["auth"], ("rzp_test_key", "test_secret"))
