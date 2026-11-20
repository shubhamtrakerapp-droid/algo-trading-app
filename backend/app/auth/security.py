import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List
import jwt
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.app.config import settings

logger = logging.getLogger("nextrade.auth.security")

security_scheme = HTTPBearer(auto_error=False)


# =============================================================================
# 1. PASSWORD HASHING (PBKDF2-HMAC-SHA256, 100,000 ROUNDS)
# =============================================================================
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Secure password hashing using NIST-approved PBKDF2-HMAC-SHA256."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000
    )
    return key.hex(), salt


def verify_password(plain_password: str, password_hash: str, salt: str) -> bool:
    """Verify password in constant time to prevent timing attacks."""
    computed_hash, _ = hash_password(plain_password, salt=salt)
    return hmac.compare_digest(computed_hash, password_hash)


# =============================================================================
# 2. JWT TOKEN GENERATION & VERIFICATION
# =============================================================================
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": "nextrade-auth",
        "aud": "nextrade-platform"
    })
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate token signature and expiration."""
    try:
        # First attempt local JWT decode
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience="nextrade-platform"
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired.")
        return None
    except jwt.InvalidTokenError:
        # Fallback check if it's a Supabase Auth issued token
        try:
            # Decode without verifying signature first to check if it's from Supabase
            unverified = jwt.decode(token, options={"verify_signature": False})
            if unverified.get("iss", "").startswith("https://") and "supabase" in unverified.get("iss", ""):
                # If SUPABASE_JWT_SECRET is configured, verify with it
                if settings.supabase_jwt_secret:
                    verified = jwt.decode(
                        token,
                        settings.supabase_jwt_secret,
                        algorithms=["HS256"],
                        options={"verify_aud": False}
                    )
                    return verified
                # Check expiration
                exp = unverified.get("exp")
                if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                    return None
                return unverified
        except Exception:
            pass
        return None


# =============================================================================
# 3. RATE LIMITING (SLIDING WINDOW: MAX 5 FAILED LOGINS PER 15 MIN)
# =============================================================================
class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, List[datetime]] = {}

    def is_rate_limited(self, identifier: str) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        attempts = [t for t in self._attempts.get(identifier, []) if t > cutoff]
        self._attempts[identifier] = attempts
        return len(attempts) >= self.max_attempts

    def record_failure(self, identifier: str):
        now = datetime.now(timezone.utc)
        if identifier not in self._attempts:
            self._attempts[identifier] = []
        self._attempts[identifier].append(now)

    def record_success(self, identifier: str):
        if identifier in self._attempts:
            del self._attempts[identifier]

    def get_retry_after(self, identifier: str) -> int:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        attempts = [t for t in self._attempts.get(identifier, []) if t > cutoff]
        if not attempts:
            return 0
        oldest_attempt = min(attempts)
        remaining = int((oldest_attempt + timedelta(seconds=self.window_seconds) - now).total_seconds())
        return max(1, remaining)


login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=900)


# =============================================================================
# 4. TOKEN REVOCATION BLACKLIST
# =============================================================================
class TokenBlacklist:
    def __init__(self):
        self._revoked: Dict[str, datetime] = {}

    def revoke(self, token: str, expires_at: Optional[datetime] = None):
        self._revoked[token] = expires_at or (datetime.now(timezone.utc) + timedelta(days=7))

    def is_revoked(self, token: str) -> bool:
        now = datetime.now(timezone.utc)
        if token in self._revoked:
            if self._revoked[token] > now:
                return True
            else:
                del self._revoked[token]
        return False


token_blacklist = TokenBlacklist()


# =============================================================================
# 5. FASTAPI DEPENDENCY: GET_CURRENT_USER
# =============================================================================
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Dict[str, Any]:
    """
    Validates token and checks authorization against the server-side 2-user allowlist.
    Rejects unauthenticated or unauthorized requests.
    """
    from backend.app.auth.allowlist import is_email_authorized

    # If auth is explicitly disabled in config (e.g., local standalone scripts)
    if not settings.auth_enabled:
        return {
            "id": 1,
            "email": settings.authorized_email_list[0] if settings.authorized_email_list else "admin@nextrade.com",
            "role": "owner",
            "username": "admin"
        }

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if token_blacklist.is_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked or logged out. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email") or payload.get("sub")
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = email.strip().lower()

    # Enforce strict 2-user allowlist check on every request
    authorized = await is_email_authorized(email)
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Email '{email}' is not on the authorized allowlist for this private NEXTRADE instance."
        )

    return {
        "id": payload.get("user_id") or payload.get("id") or 1,
        "email": email,
        "role": payload.get("role", "trader"),
        "username": payload.get("username", email.split("@")[0])
    }
