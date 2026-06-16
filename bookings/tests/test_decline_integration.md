# Test Cases — `test_decline_integration.py`

**File:** `tests/test_decline_integration.py`  
**Endpoint:** `POST /api/bookings/engagements/<pk>/action/`  
**Body:** `{"action": "decline"}`  
**Auth:** Performer token via `HTTP_AUTHORIZATION` header

---

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_performer_declines_pending` | Performer declines pending engagement → 200, status=declined |
| 2 | `test_client_cannot_decline` | Client tries to decline → 403, status unchanged |
| 3 | `test_decline_accepted_returns_400` | Decline after accept → 400, stays accepted |
| 4 | `test_decline_already_declined_returns_400` | Decline twice → first succeeds, second returns 400 |
| 5 | `test_decline_auto_expired_returns_400` | Decline past 24h → 400, stays auto_expired |
