"""Audit trail helper. Callers pass only non-sensitive metadata (field names, counts,
filter keys), never passwords, tokens, or full profile values."""
from sqlalchemy.orm import Session

from .models import AuditEvent

FORBIDDEN_KEYS = {"password", "password_hash", "token", "access_token", "refresh_token", "secret"}


def record(db: Session, actor_user_id: int | None, action: str, resource_type: str,
           resource_id: object | None = None, metadata: dict | None = None) -> None:
    clean = {k: v for k, v in (metadata or {}).items() if k.lower() not in FORBIDDEN_KEYS}
    db.add(AuditEvent(actor_user_id=actor_user_id, action=action, resource_type=resource_type,
                      resource_id=None if resource_id is None else str(resource_id),
                      metadata_json=clean or None))
