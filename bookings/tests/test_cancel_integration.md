# Test Cases — `test_cancel_integration.py`

**File:** `tests/test_cancel_integration.py`  
**Endpoint:** `POST /api/bookings/engagements/<pk>/action/`  
**Body:** `{"action": "cancel_client" | "cancel_performer", "emergency_reason": "..."}`  
**Auth:** Respective party token via `HTTP_AUTHORIZATION` header

---

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_client_cancels_pending_with_reason` | Client cancels pending with valid reason → 200, status=cancelled_client |
| 2 | `test_performer_cancels_pending_with_reason` | Performer cancels pending with valid reason → 200, status=cancelled_performer |
| 3 | `test_cancel_reason_too_short_returns_400` | Reason < 10 chars → 400 |
| 4 | `test_cancel_reason_too_long_returns_400` | Reason > 500 chars → 400 |
| 5 | `test_cancel_reason_empty_returns_400` | Empty reason → 400 |
| 6 | `test_cancel_within_24h_of_event_blocked` | Cancel within 24h of event → 400 |
| 7 | `test_performer_cannot_cancel_as_client` | Performer sends cancel_client → 403 |
| 8 | `test_client_cannot_cancel_as_performer` | Client sends cancel_performer → 403 |
| 9 | `test_cancel_already_cancelled_returns_400` | Cancel twice → second returns 400 |
| 10 | `test_cancel_client_refunds_when_paid` | Client cancel on paid engagement → refund triggered, payment_status=refunded |
| 11 | `test_cancel_performer_triggers_refund_when_paid` | Performer cancel on paid engagement → refund triggered, payment_status=refunded |
| 12 | `test_cancel_no_refund_when_unpaid` | Cancel on unpaid engagement → no refund call |
