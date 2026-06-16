# Test Cases — `test_signup_integration.py`

**File:** `tests/test_signup_integration.py`  
**Endpoint:** `POST /api/auth/signup/`  
**Fixture:** `APIClient` (no auth)

---

| # | Test Name | What It Verifies |
|---|---|---|
| 1 | `test_valid_signup_returns_token_and_creates_profile` | Valid signup → 201 with token, User + Profile with profession/location in DB, token works for `/api/auth/me/` |
| 2 | `test_duplicate_username_returns_400` | Existing username → 400, no second user created |
| 3 | `test_duplicate_email_returns_400` | Existing email → 400, no user created |
| 4 | `test_mismatched_passwords_returns_400` | password1 ≠ password2 → 400, no user created |
| 5 | `test_missing_fields_returns_400` | Missing required fields → 400, no user created |
