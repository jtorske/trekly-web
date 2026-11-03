"""Who counts as a Trekly admin, checked on the backend for every admin route.

One rule for the whole admin area (/api/admin/...): the signed-in user's id
must be in ADMIN_USER_IDS. PHOTO_ADMIN_USER_IDS, the older setting from the
trail-photo review, still counts so existing deployments keep working (see
app/config.py). The frontend only hides admin pages; it never decides.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.config import admin_user_ids
from app.models.admin import AdminAuditLog

FORBIDDEN = "Only Trekly admins can do that."


def is_admin(user_id: UUID | str) -> bool:
    return str(user_id).lower() in admin_user_ids()


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not is_admin(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)
    return user


def audit(
    db: Session,
    admin: CurrentUser,
    action: str,
    *,
    user_id: UUID | None = None,
    report_id: UUID | None = None,
    **details: Any,
) -> None:
    """Record an admin action (who, what, when, on whom) in admin_audit_log.

    Adds the row to the current transaction; the caller commits it together
    with the change it records, so one never lands without the other."""
    db.add(AdminAuditLog(
        admin_id=admin.id,
        action=action,
        target_user_id=user_id,
        target_report_id=report_id,
        details={key: value for key, value in details.items() if value is not None},
        created_at=datetime.now(timezone.utc),
    ))
