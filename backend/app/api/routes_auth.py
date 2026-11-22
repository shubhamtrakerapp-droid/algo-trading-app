import logging
from datetime import timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.models import User, AuthorizedUser
from backend.app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    login_rate_limiter,
    token_blacklist,
    get_current_user,
    security_scheme,
)
from backend.app.auth.allowlist import (
    is_email_authorized,
    get_authorized_users,
    add_authorized_user,
    remove_authorized_user,
    ensure_allowlist_seeded,
    MAX_AUTHORIZED_USERS,
)

logger = logging.getLogger("nextrade.api.auth")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# =============================================================================
# REQUEST / RESPONSE SCHEMAS
# =============================================================================
class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    reset_token: str
    new_password: str


class AddAuthorizedUserRequest(BaseModel):
    email: str
    role: Optional[str] = "trader"


# =============================================================================
# 1. LOGIN (Rate-limited, Allowlist-enforced)
# =============================================================================
@router.post("/login")
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    clean_email = req.email.strip().lower()

    # Rate limiting check
    if login_rate_limiter.is_rate_limited(clean_email):
        retry_after = login_rate_limiter.get_retry_after(clean_email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )

    # Check strict 2-user allowlist
    authorized = await is_email_authorized(clean_email, db)
    if not authorized:
        login_rate_limiter.record_failure(clean_email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Email '{clean_email}' is not on the authorized allowlist for this private instance."
        )

    # Fetch user from database
    stmt = select(User).where(func.lower(User.email) == clean_email)
    res = await db.execute(stmt)
    user = res.scalars().first()

    if not user or not user.password_hash or not user.password_salt:
        login_rate_limiter.record_failure(clean_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. If you haven't set up your password, please sign up first."
        )

    if not verify_password(req.password, user.password_hash, user.password_salt):
        login_rate_limiter.record_failure(clean_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    # Reset failure counter on successful login
    login_rate_limiter.record_success(clean_email)

    # Generate token
    token_data = {
        "sub": user.email,
        "email": user.email,
        "user_id": user.id,
        "role": user.role,
        "username": user.username or user.email.split("@")[0],
    }
    access_token = create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "role": user.role,
        }
    }


# =============================================================================
# 2. SIGNUP (Permanently Disabled - Private Invite-Only Terminal)
# =============================================================================
@router.post("/signup")
async def signup(
    req: SignupRequest,
):
    """
    Public registration is permanently disabled.
    NEXTRADE operates as a private, invite-only trading terminal.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Registration is disabled. NEXTRADE is a private invite-only terminal. Please contact the administrator."
    )


# =============================================================================
# 3. LOGOUT (Token Revocation)
# =============================================================================
@router.post("/logout")
async def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
):
    if credentials and credentials.credentials:
        token_blacklist.revoke(credentials.credentials)
    return {"status": "success", "message": "Session logged out and revoked successfully."}


# =============================================================================
# 4. CURRENT USER INFO
# =============================================================================
@router.get("/me")
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    return {"user": current_user}


# =============================================================================
# 5. PASSWORD RESET (FORGOT & RESET)
# =============================================================================
@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    clean_email = req.email.strip().lower()
    authorized = await is_email_authorized(clean_email, db)
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Email '{clean_email}' is not an authorized account."
        )

    # Generate 15-minute reset token
    reset_token = create_access_token(
        {"sub": clean_email, "email": clean_email, "type": "pwd_reset"},
        expires_delta=timedelta(minutes=15)
    )

    return {
        "status": "success",
        "message": "Password reset token generated successfully. Valid for 15 minutes.",
        "reset_token": reset_token
    }


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    clean_email = req.email.strip().lower()
    if len(req.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long."
        )

    payload = decode_access_token(req.reset_token)
    if not payload or payload.get("type") != "pwd_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )

    token_email = (payload.get("email") or payload.get("sub", "")).strip().lower()
    if token_email != clean_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token email mismatch."
        )

    # Check allowlist
    authorized = await is_email_authorized(clean_email, db)
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not authorized."
        )

    stmt = select(User).where(func.lower(User.email) == clean_email)
    res = await db.execute(stmt)
    user = res.scalars().first()

    p_hash, p_salt = hash_password(req.new_password)
    if user:
        user.password_hash = p_hash
        user.password_salt = p_salt
    else:
        user = User(
            username=clean_email.split("@")[0],
            email=clean_email,
            password_hash=p_hash,
            password_salt=p_salt,
            role="trader",
            is_active=True,
        )
        db.add(user)

    await db.commit()
    # Revoke reset token so it cannot be reused
    token_blacklist.revoke(req.reset_token)

    return {"status": "success", "message": "Password updated successfully. You can now sign in."}


# =============================================================================
# 6. ADMIN ALLOWLIST MANAGEMENT (Strict 2-User Slot Management)
# =============================================================================
@router.get("/authorized-users")
async def list_authorized_users(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """View the 2 authorized user slots and current occupants."""
    return await get_authorized_users(db)


@router.post("/authorized-users")
async def add_user_slot(
    req: AddAuthorizedUserRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add second authorized user (enforcing MAX 2 users)."""
    return await add_authorized_user(
        email=req.email,
        role=req.role or "trader",
        invited_by=current_user.get("email", "admin"),
        db=db
    )


@router.delete("/authorized-users/{email}")
async def remove_user_slot(
    email: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove an authorized user slot (cannot remove primary owner)."""
    return await remove_authorized_user(
        email=email,
        requesting_email=current_user.get("email"),
        db=db
    )
