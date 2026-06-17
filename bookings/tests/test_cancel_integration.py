from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from bookings.models import Engagement
from bookings.models import Payment


class TestCancelAPIIntegration(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_user(self, username, role="performer", profession="Saxophonist",
                     location="Mumbai", performer_fee=5000.00):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        profile.profession = profession
        profile.location = location
        if role == "performer":
            profile.is_performer = True
            profile.performer_fee = performer_fee
        else:
            profile.is_potential_client = True
            profile.client_approved = True
        profile.save()
        token = Token.objects.create(user=user)
        return user, token

    def _hire(self, performer, performer_token, client_token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")
        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Jazz gig",
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        return resp.data["id"]

    def _action(self, engagement_id, action, token, reason=""):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        payload = {"action": action}
        if reason:
            payload["emergency_reason"] = reason
        return self.client.post(
            f"/api/bookings/engagements/{engagement_id}/action/",
            payload,
            format="json",
        )

    # --- Happy path ---

    def test_client_cancels_pending_with_reason(self):
        performer, performer_token = self._create_user("performer.cancel")
        client_user, client_token = self._create_user("client.cancel", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_client", client_token,
                            reason="I found another performer for the event.")
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "cancelled_client")
        self.assertEqual(eng.cancelled_by, "client")

    def test_performer_cancels_pending_with_reason(self):
        performer, performer_token = self._create_user("performer.busy")
        client_user, client_token = self._create_user("client.cancel2", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_performer", performer_token,
                            reason="I am no longer available on that date.")
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "cancelled_performer")
        self.assertEqual(eng.cancelled_by, "performer")

    # --- Reason length validation ---

    def test_cancel_reason_too_short_returns_400(self):
        performer, performer_token = self._create_user("performer.short")
        client_user, client_token = self._create_user("client.short", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_client", client_token, reason="Short")
        self.assertEqual(resp.status_code, 400)

    def test_cancel_reason_too_long_returns_400(self):
        performer, performer_token = self._create_user("performer.long")
        client_user, client_token = self._create_user("client.long", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_client", client_token,
                            reason="x" * 501)
        self.assertEqual(resp.status_code, 400)

    def test_cancel_reason_empty_returns_400(self):
        performer, performer_token = self._create_user("performer.empty")
        client_user, client_token = self._create_user("client.empty", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_client", client_token, reason="")
        self.assertEqual(resp.status_code, 400)

    # --- 24h block ---

    def test_cancel_within_24h_of_event_blocked(self):
        performer, performer_token = self._create_user("performer.soon")
        client_user, client_token = self._create_user("client.soon", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        soon = date.today() + timedelta(days=1)
        Engagement.objects.filter(id=eng_id).update(date=soon)

        resp = self._action(eng_id, "cancel_client", client_token,
                            reason="Changed my mind, sorry about that.")
        self.assertEqual(resp.status_code, 400)

    # --- Wrong party ---

    def test_performer_cannot_cancel_as_client(self):
        performer, performer_token = self._create_user("performer.wrong")
        client_user, client_token = self._create_user("client.wrong", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_client", performer_token,
                            reason="Performer trying to use client cancel.")
        self.assertEqual(resp.status_code, 403)

    def test_client_cannot_cancel_as_performer(self):
        performer, performer_token = self._create_user("performer.wrong2")
        client_user, client_token = self._create_user("client.wrong2", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_performer", client_token,
                            reason="Client trying to use performer cancel.")
        self.assertEqual(resp.status_code, 403)

    # --- Terminal state ---

    def test_cancel_already_cancelled_returns_400(self):
        performer, performer_token = self._create_user("performer.done")
        client_user, client_token = self._create_user("client.done", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        self._action(eng_id, "cancel_client", client_token,
                     reason="First cancellation with a valid reason.")
        resp = self._action(eng_id, "cancel_client", client_token,
                            reason="Trying to cancel again, still valid.")
        self.assertEqual(resp.status_code, 400)

    # --- Refund on paid engagement ---

    @patch("bookings.services.payments.get_client")
    def test_cancel_client_refunds_when_paid(self, mock_get_client):
        mock_razorpay = mock_get_client.return_value
        mock_razorpay.payment.refund.return_value = {"id": "rfnd_test123"}

        performer, performer_token = self._create_user("performer.paid")
        client_user, client_token = self._create_user("client.paid", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        Engagement.objects.filter(id=eng_id).update(
            payment_status=Engagement.PAYMENT_PAID
        )
        Payment.objects.create(
            engagement_id=eng_id,
            amount=5000,
            razorpay_order_id="order_test",
            razorpay_payment_id="pay_test",
            status="captured",
        )

        resp = self._action(eng_id, "cancel_client", client_token,
                            reason="Client cancelled with a legitimate reason.")
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.payment_status, Engagement.PAYMENT_REFUNDED)
        self.assertIsNotNone(eng.refunded_at)
        mock_razorpay.payment.refund.assert_called_once()

    @patch("bookings.services.payments.get_client")
    def test_cancel_performer_triggers_refund_when_paid(self, mock_get_client):
        mock_razorpay = mock_get_client.return_value
        mock_razorpay.payment.refund.return_value = {"id": "rfnd_test456"}

        performer, performer_token = self._create_user("performer.paid2")
        client_user, client_token = self._create_user("client.paid2", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        Engagement.objects.filter(id=eng_id).update(
            payment_status=Engagement.PAYMENT_PAID
        )
        Payment.objects.create(
            engagement_id=eng_id,
            amount=5000,
            razorpay_order_id="order_test2",
            razorpay_payment_id="pay_test2",
            status="captured",
        )

        resp = self._action(eng_id, "cancel_performer", performer_token,
                            reason="Performer cancelled with a valid reason.")
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.payment_status, Engagement.PAYMENT_REFUNDED)
        self.assertIsNotNone(eng.refunded_at)
        mock_razorpay.payment.refund.assert_called_once()

    @patch("bookings.services.payments.get_client")
    def test_cancel_no_refund_when_unpaid(self, mock_get_client):
        mock_razorpay = mock_get_client.return_value

        performer, performer_token = self._create_user("performer.unpaid")
        client_user, client_token = self._create_user("client.unpaid", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "cancel_client", client_token,
                            reason="Cancelling before payment, no refund needed.")
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.payment_status, Engagement.PAYMENT_UNPAID)
        mock_razorpay.payment.refund.assert_not_called()