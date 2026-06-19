"""
AUTHENTICATION API

JWT access + refresh tokens, email verification, password reset, RBAC.
Email sending is not wired to a real SMTP server (no paid/external
dependency required) - verification/reset tokens are returned directly in
the API response and logged server-side, so the flow is fully testable
offline. Wire in smtplib / an email provider in send_email() to go to
production with real email delivery.
"""
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserSession, RoleEnum
from app.schemas.auth import (RegisterRequest, LoginRequest, TokenResponse, RefreshRequest,
                               ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest, UserOut)
from app.core.security import (hash_password, verify_password, create_access_token,
                                create_refresh_token, decode_refresh_token, generate_token)
from app.core.rbac import get_current_user
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger("cis.auth")


def send_email(to: str, subject: str, body: str):
    """Stub mailer - logs instead of sending. Swap in real SMTP/provider here."""
    logger.info(f"[EMAIL to {to}] {subject}\n{body}")


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # First registered user becomes admin automatically (bootstrap convenience)
    is_first_user = db.query(User).count() == 0
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=RoleEnum.ADMIN if is_first_user else RoleEnum.USER,
        email_verification_token=generate_token(16),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    send_email(user.email, "Verify your CIS account",
               f"Your verification token: {user.email_verification_token}")
    log_action(db, user.id, "user_registered", "user", user.id)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    access_token = create_access_token(user.id, user.role.value)
    refresh_token, expires_at = create_refresh_token(user.id)

    db.add(UserSession(
        user_id=user.id, refresh_token=refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        expires_at=expires_at,
    ))
    log_action(db, user.id, "user_login", "user", user.id,
               ip_address=request.client.host if request.client else None)
    db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    decoded = decode_refresh_token(payload.refresh_token)
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    session = db.query(UserSession).filter(
        UserSession.refresh_token == payload.refresh_token, UserSession.revoked == False  # noqa: E712
    ).first()
    if not session or session.expires_at < dt.datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token is revoked or expired")

    user = db.query(User).filter(User.id == decoded["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    new_access = create_access_token(user.id, user.role.value)
    new_refresh, expires_at = create_refresh_token(user.id)

    session.revoked = True
    db.add(UserSession(user_id=user.id, refresh_token=new_refresh, expires_at=expires_at))
    db.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.refresh_token == payload.refresh_token).first()
    if session:
        session.revoked = True
        db.commit()
    return


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/verify-email", response_model=UserOut)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_verification_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user.is_email_verified = True
    user.email_verification_token = None
    db.commit()
    return user


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        user.password_reset_token = generate_token(16)
        user.password_reset_expires = dt.datetime.utcnow() + dt.timedelta(hours=1)
        db.commit()
        send_email(user.email, "Reset your CIS password",
                   f"Your reset token: {user.password_reset_token}")
    # Always return 200 regardless of whether the email exists (avoid account enumeration)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.password_reset_token == payload.token).first()
    if not user or not user.password_reset_expires or user.password_reset_expires < dt.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = hash_password(payload.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()
    return {"message": "Password reset successful"}
