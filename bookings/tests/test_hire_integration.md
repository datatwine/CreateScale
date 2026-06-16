# Test Cases — `test_hire_integration.py`

**File:** `tests/test_hire_integration.py`  
**Endpoint:** `POST /api/bookings/hire/<performer_id>/`  
**Auth:** Client token via `HTTP_AUTHORIZATION` header

---

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_hire_creates_pending_engagement_with_fee` | Approved client hires performer → 201, Engagement status=pending, fee snapshotted from profile |
| 2 | `test_hire_snapshots_performer_fee_at_hire_time` | Fee change after hire still uses old fee for existing, new fee for fresh hire |
| 3 | `test_hire_rejected_when_client_is_performer` | Performer-only user hires themselves → 400, no engagement created |
| 4 | `test_dual_role_user_cannot_self_hire` | User with both client+performer roles tries to self-hire → 400 |
| 5 | `test_hire_rejected_for_nonexistent_performer` | Non-existent performer ID → 404 |
| 5 | `test_hire_past_date_is_accepted` | Past date is allowed (no date validation) → 201 |
| 6 | `test_duplicate_hire_same_client_same_performer_same_date_rejected` | Same client+performer+date twice → 201 then 400 |
| 7 | `test_duplicate_allowed_for_different_date` | Same client+performer, different date → both succeed (201) |
| 8 | `test_duplicate_allowed_for_different_performer` | Same client+date, different performer → both succeed (201) |
| 9 | `test_hire_capped_at_three_pending_engagements` | Client has 3 pending/accepted → 4th returns 400, only 3 exist |
