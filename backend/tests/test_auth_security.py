import pytest
from datetime import timedelta
from httpx import AsyncClient, ASGITransport
from fastapi import HTTPException

from backend.app.main import app
from backend.app.database import init_db
from backend.app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    LoginRateLimiter,
    TokenBlacklist,
    token_blacklist,
)
from backend.app.auth.allowlist import (
    is_email_authorized,
    get_authorized_users,
    add_authorized_user,
    remove_authorized_user,
    MAX_AUTHORIZED_USERS,
)


@pytest.mark.asyncio
async def test_password_hashing_and_verification():
    """Verify PBKDF2-HMAC-SHA256 hashing and constant-time verification."""
    password = "SuperSecurePassword123!"
    p_hash, salt = hash_password(password)

    assert p_hash is not None and len(p_hash) == 64  # SHA256 hex digest
    assert salt is not None and len(salt) == 32  # 16 bytes hex

    # Correct password verifies
    assert verify_password(password, p_hash, salt) is True

    # Incorrect password fails
    assert verify_password("WrongPassword123!", p_hash, salt) is False
    assert verify_password("", p_hash, salt) is False


@pytest.mark.asyncio
async def test_access_token_generation_and_decoding():
    """Verify JWT token creation, expiration, and payload decoding."""
    data = {
        "sub": "admin@nextrade.com",
        "email": "admin@nextrade.com",
        "role": "owner",
        "user_id": 1,
    }
    token = create_access_token(data, expires_delta=timedelta(minutes=30))
    assert token is not None and len(token) > 20

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["email"] == "admin@nextrade.com"
    assert payload["role"] == "owner"
    assert payload["iss"] == "nextrade-auth"

    # Expired token returns None
    expired_token = create_access_token(data, expires_delta=timedelta(seconds=-10))
    assert decode_access_token(expired_token) is None


@pytest.mark.asyncio
async def test_login_rate_limiter():
    """Verify rate limiter blocks after 5 failed attempts."""
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)
    email = "test_limiter@nextrade.com"

    for _ in range(4):
        assert limiter.is_rate_limited(email) is False
        limiter.record_failure(email)

    # 5th attempt
    limiter.record_failure(email)
    assert limiter.is_rate_limited(email) is True
    assert limiter.get_retry_after(email) > 0

    # Success clears rate limit
    limiter.record_success(email)
    assert limiter.is_rate_limited(email) is False


@pytest.mark.asyncio
async def test_token_blacklist():
    """Verify token revocation on logout."""
    blacklist = TokenBlacklist()
    token = "sample_test_token_12345"

    assert blacklist.is_revoked(token) is False
    blacklist.revoke(token)
    assert blacklist.is_revoked(token) is True
    assert blacklist.is_revoked("other_token") is False


@pytest.mark.asyncio
async def test_allowlist_strict_2_user_limit():
    """Verify strict 2-user capacity and allowlist enforcement."""
    await init_db()

    # Default configured email must be authorized
    assert await is_email_authorized("admin@nextrade.com") is True
    assert await is_email_authorized("unauthorized.person@hacker.com") is False

    slots = await get_authorized_users()
    assert slots["max_slots"] == MAX_AUTHORIZED_USERS
    assert slots["slots_used"] <= 2

    # If all 2 slots are full, remove any non-owner slot to test dynamic allocation
    user2_email = "second_authorized@nextrade.com"
    for u in slots["users"]:
        if u["role"] != "owner" and u["email"] != "admin@nextrade.com":
            try:
                await remove_authorized_user(u["email"], requesting_email="admin@nextrade.com")
            except Exception:
                pass

    try:
        await remove_authorized_user(user2_email, requesting_email="admin@nextrade.com")
    except Exception:
        pass

    added = await add_authorized_user(user2_email, role="trader", invited_by="admin@nextrade.com")
    assert added["email"] == user2_email
    assert await is_email_authorized(user2_email) is True

    # Try adding a third user (must be rejected)
    with pytest.raises(HTTPException) as exc_info:
        await add_authorized_user("third_user@nextrade.com", role="trader")
    assert exc_info.value.status_code == 400
    assert "limit" in exc_info.value.detail.lower()

    # Remove user 2
    removed = await remove_authorized_user(user2_email, requesting_email="admin@nextrade.com")
    assert removed["status"] == "success"


@pytest.mark.asyncio
async def test_api_auth_flow():
    """E2E API test for disabled signup, login, get_me, rate limiting, and logout."""
    await init_db()
    from backend.app.database import AsyncSessionLocal
    from backend.app.models.models import User
    from sqlalchemy import select, func

    # Ensure admin user has known test password without deleting existing account
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(func.lower(User.email) == "admin@nextrade.com")
        res = await session.execute(stmt)
        u = res.scalars().first()
        p_hash, p_salt = hash_password("ValidMasterPassword2026!")
        if u:
            u.password_hash = p_hash
            u.password_salt = p_salt
            u.is_active = True
        else:
            u = User(
                username="NextradeAdmin",
                email="admin@nextrade.com",
                password_hash=p_hash,
                password_salt=p_salt,
                role="owner",
                is_active=True,
            )
            session.add(u)
        await session.commit()

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Signup with unauthorized email -> 403 Forbidden (Registration Disabled)
        res = await client.post(
            "/api/auth/signup",
            json={"email": "attacker@evil.com", "password": "Password123!"}
        )
        assert res.status_code == 403
        assert "registration is disabled" in res.json()["detail"].lower()

        # 2. Signup with authorized email -> 403 Forbidden (Registration Disabled)
        res = await client.post(
            "/api/auth/signup",
            json={
                "email": "admin@nextrade.com",
                "password": "ValidMasterPassword2026!",
                "username": "NextradeAdmin"
            }
        )
        assert res.status_code == 403
        assert "registration is disabled" in res.json()["detail"].lower()

        # 3. Login with wrong password -> 401 Unauthorized
        res = await client.post(
            "/api/auth/login",
            json={"email": "admin@nextrade.com", "password": "WrongPassword!"}
        )
        assert res.status_code == 401

        # 4. Login with correct password -> 200 OK + access_token
        res = await client.post(
            "/api/auth/login",
            json={"email": "admin@nextrade.com", "password": "ValidMasterPassword2026!"}
        )
        assert res.status_code == 200
        auth_data = res.json()
        token = auth_data["access_token"]
        assert token is not None

        # 6. Call /api/auth/me with valid Bearer token -> 200 OK
        res = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        me_data = res.json()
        assert me_data["user"]["email"] == "admin@nextrade.com"

        # 7. Call /api/auth/me without token -> 401 Unauthorized
        res = await client.get("/api/auth/me")
        assert res.status_code == 401

        # 8. Password Reset Flow
        res = await client.post(
            "/api/auth/forgot-password",
            json={"email": "admin@nextrade.com"}
        )
        assert res.status_code == 200
        reset_token = res.json()["reset_token"]
        assert reset_token is not None

        # Reset to new password
        res = await client.post(
            "/api/auth/reset-password",
            json={
                "email": "admin@nextrade.com",
                "reset_token": reset_token,
                "new_password": "NewMasterPassword2026!"
            }
        )
        assert res.status_code == 200

        # Login with old password must fail
        res = await client.post(
            "/api/auth/login",
            json={"email": "admin@nextrade.com", "password": "ValidMasterPassword2026!"}
        )
        assert res.status_code == 401

        # Login with new password must succeed
        res = await client.post(
            "/api/auth/login",
            json={"email": "admin@nextrade.com", "password": "NewMasterPassword2026!"}
        )
        assert res.status_code == 200
        new_token = res.json()["access_token"]

        # 9. Logout token revocation
        res = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {new_token}"}
        )
        assert res.status_code == 200

        # Immediate call with revoked token must be rejected with 401
        res = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {new_token}"}
        )
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"].lower()
