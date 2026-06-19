"""
ADMIN PANEL API - Users, Datasets overview, Storage, Active Jobs, Health, Audit Logs
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User, RoleEnum
from app.models.dataset import Dataset
from app.models.model_test import ModelTest
from app.models.audit import AuditLog
from app.core.rbac import require_admin
from app.services import scheduler as scheduler_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role.value,
             "is_active": u.is_active, "is_email_verified": u.is_email_verified,
             "created_at": u.created_at} for u in rows]


@router.patch("/users/{user_id}/role")
def change_user_role(user_id: str, role: RoleEnum, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    db.commit()
    log_action(db, admin.id, "user_role_changed", "user", user_id, details={"new_role": role.value})
    return {"message": "Role updated", "user_id": user_id, "role": role.value}


@router.patch("/users/{user_id}/status")
def toggle_user_active(user_id: str, is_active: bool, db: Session = Depends(get_db),
                        admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = is_active
    db.commit()
    log_action(db, admin.id, "user_status_changed", "user", user_id, details={"is_active": is_active})
    return {"message": "Status updated", "user_id": user_id, "is_active": is_active}


@router.get("/audit-logs")
def get_audit_logs(limit: int = 200, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": a.id, "user_id": a.user_id, "action": a.action, "resource_type": a.resource_type,
             "resource_id": a.resource_id, "details": a.details, "ip_address": a.ip_address,
             "created_at": a.created_at} for a in rows]


@router.get("/system-health")
def system_health(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    total, used, free = shutil.disk_usage(settings.STORAGE_DIR)
    return {
        "users": db.query(User).count(),
        "datasets": db.query(Dataset).count(),
        "models": db.query(ModelTest).count(),
        "active_monitoring_jobs": len(scheduler_service.scheduler.get_jobs()),
        "storage": {
            "total_gb": round(total / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
        },
        "dataset_storage_mb": round(
            sum(f.stat().st_size for f in Path(settings.DATASET_DIR).rglob("*") if f.is_file())
            / (1024 * 1024), 2
        ) if Path(settings.DATASET_DIR).exists() else 0,
    }


@router.get("/active-jobs")
def active_jobs(admin: User = Depends(require_admin)):
    jobs = scheduler_service.scheduler.get_jobs()
    return [{"id": j.id, "next_run_time": str(j.next_run_time), "trigger": str(j.trigger)} for j in jobs]
