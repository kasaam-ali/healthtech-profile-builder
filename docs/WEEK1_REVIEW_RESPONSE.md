# Week 1 — Response to PR #2 security review (@AhmedHashir10)

Fixes commit: `e7310e6` on `week-1-auth-foundations`. Scope: Week 1 auth only (no profile CRUD/ML).

| # | Review item | Change | Test / evidence (`backend/tests/`) |
|---|---|---|---|
| P1 | Fail closed on deployment secrets | `config.py`: `ENVIRONMENT` (default **production**). Dev defaults only when `ENVIRONMENT=development`; production raises `InsecureConfigError` at import/startup if `JWT_SECRET`/`SESSION_SECRET` missing, <32 chars, known default/placeholder, or equal | `test_production_rejects_missing_weak_or_default_secrets` (5 cases), `test_environment_defaults_to_production_and_fails_closed`, `test_app_startup_refuses_unconfigured_production` (real `import app.main` subprocess), `test_app_startup_ok_with_strong_production_secrets` |
| P1 | Env-aware secure cookie | `main.py`: `https_only=settings.is_production` | `test_production_accepts_strong_secrets_and_secure_cookie`, `test_development_uses_explicit_local_defaults_and_http_cookie`; README "Configuration: local vs production" |
| P2 | Revocable admin sessions | New `admin_sessions` table (opaque `token_urlsafe(32)` id, user_id, created_at, expires_at, revoked). Cookie holds only the id. Login rotates (revokes old id), logout revokes server record. `current_admin` checks record + `users.is_admin` | `test_cookie_holds_only_opaque_id_stored_server_side`, `test_logout_replay_of_saved_cookie_is_rejected`, `test_login_rotates_session_id`, `test_demoted_admin_session_is_rejected` |
| P2 | bcrypt 72 UTF-8 bytes | `schemas.py` validator on SignupIn **and** LoginIn rejects >72 bytes with 422 "Password must be at most 72 bytes when UTF-8 encoded"; `security.py` refuses to hash/verify >72 bytes (defence in depth) | `test_ascii_72_bytes_ok_73_rejected`, `test_multibyte_under_72_chars_over_72_bytes_rejected` (37×"é" = 74 bytes rejected; 36×"é" = 72 OK), `test_login_also_enforces_byte_limit` |
| CSRF | Explicit policy for cookie mutations | `deps.require_trusted_origin` on `/admin/login` + `/admin/logout`: Origin (or Referer fallback) must be in `CORS_ORIGINS`, else 403. Policy in README | `test_admin_login_requires_trusted_origin` (missing / evil Origin / evil Referer → 403, trusted Referer → 200), `test_admin_logout_requires_trusted_origin` |
| Tests | Expiry / tampering / logout replay | — | `test_expired_session_is_rejected`, `test_tampered_cookie_is_rejected`, `test_logout_replay_of_saved_cookie_is_rejected` |
| Follow-up | Refresh token reuse | **Documented** (README Auth design): reusable until 7-day expiry, blast radius, mitigation = rotate `JWT_SECRET`; rotation+reuse detection planned | README; existing `test_refresh_token_cannot_be_used_as_access` |
| Follow-up | Admins getting member JWTs | **Policy: blocked.** `/auth/login` → 403 for admins; `/auth/refresh` rejects admin ids. Admins only use the session | `test_admin_cannot_get_member_jwt`; boundary also `test_user_jwt_cannot_access_admin`, `test_signup_cannot_make_admin` |
| Demo | Member/admin boundary + negatives tied to commit | pytest output below (run on `e7310e6`) | below |

## `pytest -v` on e7310e6
```
tests/test_auth.py::test_unauthenticated_me_fails PASSED
tests/test_auth.py::test_signup_login_me PASSED
tests/test_auth.py::test_wrong_password_and_duplicate PASSED
tests/test_auth.py::test_password_is_hashed PASSED
tests/test_auth.py::test_refresh_token_cannot_be_used_as_access PASSED
tests/test_auth.py::test_signup_cannot_make_admin PASSED
tests/test_auth.py::test_user_jwt_cannot_access_admin PASSED
tests/test_auth.py::test_unauthenticated_admin_fails PASSED
tests/test_auth.py::test_admin_session_flow PASSED
tests/test_security_review.py::test_production_rejects_missing_weak_or_default_secrets
tests/test_security_review.py::test_production_rejects_missing_weak_or_default_secrets
tests/test_security_review.py::test_production_rejects_missing_weak_or_default_secrets
tests/test_security_review.py::test_production_rejects_missing_weak_or_default_secrets
tests/test_security_review.py::test_production_rejects_missing_weak_or_default_secrets
tests/test_security_review.py::test_environment_defaults_to_production_and_fails_closed PASSED
tests/test_security_review.py::test_production_accepts_strong_secrets_and_secure_cookie PASSED
tests/test_security_review.py::test_development_uses_explicit_local_defaults_and_http_cookie PASSED
tests/test_security_review.py::test_app_startup_refuses_unconfigured_production PASSED
tests/test_security_review.py::test_app_startup_ok_with_strong_production_secrets PASSED
tests/test_security_review.py::test_cookie_holds_only_opaque_id_stored_server_side PASSED
tests/test_security_review.py::test_logout_replay_of_saved_cookie_is_rejected PASSED
tests/test_security_review.py::test_login_rotates_session_id PASSED
tests/test_security_review.py::test_expired_session_is_rejected PASSED
tests/test_security_review.py::test_tampered_cookie_is_rejected PASSED
tests/test_security_review.py::test_demoted_admin_session_is_rejected PASSED
tests/test_security_review.py::test_admin_login_requires_trusted_origin PASSED
tests/test_security_review.py::test_admin_logout_requires_trusted_origin PASSED
tests/test_security_review.py::test_ascii_72_bytes_ok_73_rejected PASSED
tests/test_security_review.py::test_multibyte_under_72_chars_over_72_bytes_rejected PASSED
tests/test_security_review.py::test_login_also_enforces_byte_limit PASSED
tests/test_security_review.py::test_admin_cannot_get_member_jwt PASSED
============================= 31 passed in 12.16s ==============================
```
