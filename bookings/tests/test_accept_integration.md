# Test Cases — `test_accept_integration.py`

**File:** `tests/test_accept_integration.py`  
**Endpoint:** `POST /api/bookings/engagements/<pk>/action/`  
**Body:** `{"action": "accept"}`  
**Auth:** Performer token via `HTTP_AUTHORIZATION` header

---

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_performer_accepts_engagement` | Performer accepts pending engagement → 200, status=accepted |
| 2 | `test_performer_accept_auto_cancels_same_date_pending` | Accept one → other pending for same performer+date get status=cancelled_performer |
| 3 | `test_performer_accept_fails_after_24h` | Accept after 24h of creation → 400, engagement auto-expired |
| 4 | `test_accept_fails_when_performer_conflict_exists` | Performer with accepted booking tries to accept another on same date → 400/409, stays pending |
| 5 | `test_client_cannot_accept_their_own_engagement` | Client tries to accept → 403, status unchanged |
| 6 | `test_double_accept_returns_400` | Accept twice → first succeeds, second returns 400 |
