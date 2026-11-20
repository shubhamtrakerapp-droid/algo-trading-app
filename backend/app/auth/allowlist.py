import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal
from backend.app.models.models import AuthorizedUser

logger = logging.getLogger("nextrade.auth.allowlist")

MAX_AUTHORIZED_USERS: int = 2


async def ensure_allowlist_seeded(db: AsyncSession) -> None:
    """
    Ensure the database authorized_users table is seeded from configured settings
    up to the strict limit of MAX_AUTHORIZED_USERS (2).
    """
    try:
        stmt = select(func.count(AuthorizedUser.id))
        result = await db.execute(stmt)
        count = result.scalar() or 0

        configured_emails = settings.authorized_email_list
        if count == 0 and configured_emails:
            # Seed up to 2 configured emails
            for idx, raw_email in enumerate(configured_emails[:MAX_AUTHORIZED_USERS]):
                clean_email = raw_email.strip().lower()
                role = "owner" if idx == 0 else "trader"
                user_auth = AuthorizedUser(
                    email=clean_email,
                    role=role,
                    is_active=True,
                    invited_by="system_config"
                )
                db.add(user_auth)
            await db.commit()
            logger.info("Seeded %d authorized user(s) into database.", min(len(configured_emails), MAX_AUTHORIZED_USERS))
    except Exception as exc:
        logger.error("Error seeding authorized users allowlist: %s", exc)
        await db.rollback()


async def is_email_authorized(email: str, db: Optional[AsyncSession] = None) -> bool:
    """
    Check if an email address is authorized in the strict 2-user private allowlist.
    """
    if not email:
        return False

    clean_email = email.strip().lower()

    # Fast-path check against configured authorized email list
    if clean_email in settings.authorized_email_list:
        return True

    # Check database
    if db is not None:
        return await _check_db_authorized(clean_email, db)

    async with AsyncSessionLocal() as session:
        return await _check_db_authorized(clean_email, session)


async def _check_db_authorized(clean_email: str, session: AsyncSession) -> bool:
    try:
        stmt = select(AuthorizedUser).where(
            func.lower(AuthorizedUser.email) == clean_email,
            AuthorizedUser.is_active == True
        )
        result = await session.execute(stmt)
        record = result.scalars().first()
        return record is not None
    except Exception as exc:
        logger.error("Failed to query authorized_users table: %s", exc)
        # Fallback to configured settings
        return clean_email in settings.authorized_email_list


async def get_authorized_users(db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Retrieve all authorized user slots (max 2) and current occupancy.
    """
    async def _query(session: AsyncSession) -> Dict[str, Any]:
        await ensure_allowlist_seeded(session)
        stmt = select(AuthorizedUser).order_by(AuthorizedUser.created_at.asc())
        result = await session.execute(stmt)
        records = result.scalars().all()

        users_list = [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "invited_by": u.invited_by,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in records
        ]
        return {
            "max_slots": MAX_AUTHORIZED_USERS,
            "slots_used": len(users_list),
            "slots_available": max(0, MAX_AUTHORIZED_USERS - len(users_list)),
            "users": users_list
        }

    if db is not None:
        return await _query(db)

    async with AsyncSessionLocal() as session:
        return await _query(session)


async def add_authorized_user(
    email: str,
    role: str = "trader",
    invited_by: Optional[str] = None,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Add a new authorized user to the private allowlist, enforcing the MAX_AUTHORIZED_USERS (2) limit.
    """
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid email address is required."
        )

    clean_email = email.strip().lower()

    async def _add(session: AsyncSession) -> Dict[str, Any]:
        await ensure_allowlist_seeded(session)

        # Check existing
        stmt = select(AuthorizedUser).where(func.lower(AuthorizedUser.email) == clean_email)
        result = await session.execute(stmt)
        existing = result.scalars().first()

        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.role = role
                await session.commit()
                return {
                    "id": existing.id,
                    "email": existing.email,
                    "role": existing.role,
                    "is_active": existing.is_active,
                    "created_at": existing.created_at.isoformat() if existing.created_at else None
                }
            return {
                "id": existing.id,
                "email": existing.email,
                "role": existing.role,
                "is_active": existing.is_active,
                "created_at": existing.created_at.isoformat() if existing.created_at else None
            }

        # Check capacity
        count_stmt = select(func.count(AuthorizedUser.id)).where(AuthorizedUser.is_active == True)
        count_res = await session.execute(count_stmt)
        active_count = count_res.scalar() or 0

        if active_count >= MAX_AUTHORIZED_USERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum authorized user limit ({MAX_AUTHORIZED_USERS}) reached. Remove an existing user first."
            )

        new_auth = AuthorizedUser(
            email=clean_email,
            role=role if role in ("owner", "admin", "trader") else "trader",
            is_active=True,
            invited_by=invited_by or "admin"
        )
        session.add(new_auth)
        await session.commit()
        await session.refresh(new_auth)

        logger.info("Added authorized user: %s (role: %s)", clean_email, new_auth.role)
        return {
            "id": new_auth.id,
            "email": new_auth.email,
            "role": new_auth.role,
            "is_active": new_auth.is_active,
            "created_at": new_auth.created_at.isoformat() if new_auth.created_at else None
        }

    if db is not None:
        return await _add(db)

    async with AsyncSessionLocal() as session:
        return await _add(session)


async def remove_authorized_user(
    email: str,
    requesting_email: Optional[str] = None,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Remove or deactivate an authorized user slot.
    Cannot remove the primary owner or yourself if you are the only user.
    """
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required."
        )

    clean_email = email.strip().lower()

    async def _remove(session: AsyncSession) -> Dict[str, Any]:
        stmt = select(AuthorizedUser).where(func.lower(AuthorizedUser.email) == clean_email)
        result = await session.execute(stmt)
        record = result.scalars().first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{clean_email}' not found in authorized allowlist."
            )

        if record.role == "owner" and requesting_email and clean_email == requesting_email.strip().lower():
            # Check if there are other owners
            other_owners_stmt = select(func.count(AuthorizedUser.id)).where(
                AuthorizedUser.role == "owner",
                func.lower(AuthorizedUser.email) != clean_email,
                AuthorizedUser.is_active == True
            )
            other_res = await session.execute(other_owners_stmt)
            if (other_res.scalar() or 0) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove the primary owner account."
                )

        await session.delete(record)
        await session.commit()
        logger.info("Removed authorized user: %s", clean_email)
        return {"status": "success", "message": f"User {clean_email} removed from authorized allowlist."}

    if db is not None:
        return await _remove(db)

    async with AsyncSessionLocal() as session:
        return await _remove(session)
