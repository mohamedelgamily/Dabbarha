"""Temporary, read-only and per-request-MFA financial support access."""
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_db
from app.api.routes.admin import admin_api_gate, require_operational_admin
from app.models.admin_audit import AdminAuditEvent
from app.models.admin_support import FinancialSupportGrant
from app.models.auth_session import AuthSession
from app.models.notifications import PaymentOccurrence
from app.models.obligation import Obligation, ObligationInstallment
from app.models.user import User
from app.schemas.admin_support import (
    FinancialProfileSupportResponse, SupportGrantApproval, SupportGrantCreate,
    SupportGrantResponse, SupportInstallmentPage, SupportObligationPage,
    SupportPaymentStatus, SupportPaymentStatusPage,
)
from app.services.admin_security import decrypt_totp_secret, matching_totp_step, write_audit
from app.services.admin_operations import apply_read_timeout

router = APIRouter(dependencies=[Depends(admin_api_gate)])
GRANT_MAX_SECONDS = 15 * 60
READ_PAGE_MAX = 50
READ_OFFSET_MAX = 1000
SCOPE_SET = {"financial_profile", "obligations", "installments", "payment_statuses"}


def _start_write_lock(db):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    elif db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('lock_timeout', '3s', true)"))


def _record(db, request, action, outcome, actor_id, target_id=None, grant_id=None):
    key = request.app.state.security.settings.hmac_key
    from app.core.api_security import source_ip
    write_audit(db, key, action, outcome, actor_id=actor_id, target_id=target_id,
                source=source_ip(request.scope), support_grant_id=grant_id)


def _commit_or_unavailable(db):
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Support access is temporarily unavailable.",
                            headers={"Retry-After": "1"}) from None


def _superadmin(request: Request, actor: User, db) -> str:
    payload = request.state.auth_payload
    if actor.admin_role != "superadmin" or payload.get("admin_role") != "superadmin":
        _record(db, request, "support_financial_denied", "failure", actor.id)
        _commit_or_unavailable(db)
        raise HTTPException(403, "Superadministrator access is required.")
    sid = payload.get("sid")
    if not isinstance(sid, str) or not sid:
        _record(db, request, "support_financial_denied", "failure", actor.id)
        _commit_or_unavailable(db)
        raise HTTPException(401, "A current device session is required.")
    return sid


def _response(grant: FinancialSupportGrant, now: int) -> SupportGrantResponse:
    effective = "expired" if grant.status in {"pending", "active"} and grant.expires_at <= now else grant.status
    return SupportGrantResponse(
        grant_id=grant.id, target_user_id=grant.target_user_id,
        support_case_reference=grant.support_case_reference, reason_code=grant.reason_code,
        scopes=grant.scopes, status=effective, self_approved=grant.self_approved,
        requested_at=grant.requested_at, approved_at=grant.approved_at,
        expires_at=grant.expires_at, revoked_at=grant.revoked_at,
    )


def _lock_current_admin_session(db, request, actor, sid):
    now = int(time.time())
    apply_read_timeout(db)
    admin = db.scalar(select(User).where(User.id == actor.id).with_for_update()
                       .execution_options(populate_existing=True))
    session = db.scalar(select(AuthSession).where(
        AuthSession.id == sid, AuthSession.user_id == actor.id,
        AuthSession.revoked_at.is_(None), AuthSession.idle_expires_at > now,
        AuthSession.absolute_expires_at > now,
    ).with_for_update().execution_options(populate_existing=True))
    if admin is None or admin.admin_role != "superadmin" or session is None:
        _denied(db, request, actor, None, "Administrator access is no longer valid.", 403)


def _denied(db, request, actor, target_id, detail="Support grant is unavailable.", code=403, grant_id=None):
    try:
        _record(db, request, "support_financial_denied", "failure", actor.id, target_id, grant_id)
        _commit_or_unavailable(db)
    except HTTPException:
        raise
    raise HTTPException(code, detail)


@router.post("/support-grants", response_model=SupportGrantResponse, status_code=201)
def create_support_grant(body: SupportGrantCreate, request: Request,
                         actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    sid = _superadmin(request, actor, db)
    now = int(time.time())
    if not set(body.scopes) <= SCOPE_SET:
        _denied(db, request, actor, body.target_user_id, "The requested support scope is invalid.", 422)
    try:
        _start_write_lock(db)
        _lock_current_admin_session(db, request, actor, sid)
        target = db.scalar(select(User).where(User.id == body.target_user_id).with_for_update())
        if target is None:
            _denied(db, request, actor, None, "Account not found.", 404)
        expired = db.scalars(select(FinancialSupportGrant).where(
            FinancialSupportGrant.target_user_id == target.id,
            FinancialSupportGrant.requester_session_id == sid,
            FinancialSupportGrant.status.in_(["pending", "active"]),
            FinancialSupportGrant.expires_at <= now,
        ).with_for_update()).all()
        for previous in expired:
            previous.status = "expired"
            _record(db, request, "support_grant_expired", "success", actor.id, target.id, previous.id)
        existing = db.scalar(select(FinancialSupportGrant).where(
            FinancialSupportGrant.target_user_id == target.id,
            FinancialSupportGrant.requester_session_id == sid,
            FinancialSupportGrant.status.in_(["pending", "active"]),
            FinancialSupportGrant.expires_at > now,
        ).limit(1))
        if existing is not None:
            _denied(db, request, actor, target.id, "An unexpired support grant already exists for this account and session.", 409)
        grant = FinancialSupportGrant(
            id=str(uuid4()), target_user_id=target.id, requester_user_id=actor.id,
            requester_session_id=sid, support_case_reference=body.support_case_reference,
            reason_code=body.reason_code, scopes=body.scopes, status="pending",
            requested_at=now, expires_at=now + GRANT_MAX_SECONDS,
        )
        db.add(grant)
        db.flush()
        _record(db, request, "support_grant_requested", "success", actor.id, target.id, grant.id)
        _commit_or_unavailable(db)
        return _response(grant, now)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Support access is temporarily unavailable.", headers={"Retry-After": "1"}) from None


@router.post("/support-grants/{grant_id}/approve", response_model=SupportGrantResponse)
def approve_support_grant(grant_id: str, body: SupportGrantApproval, request: Request,
                          actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    sid = _superadmin(request, actor, db)
    now = int(time.time())
    try:
        _start_write_lock(db)
        _lock_current_admin_session(db, request, actor, sid)
        target_id = db.scalar(select(FinancialSupportGrant.target_user_id).where(
            FinancialSupportGrant.id == grant_id))
        if target_id is None:
            _denied(db, request, actor, None)
        target = db.scalar(select(User.id).where(User.id == target_id).with_for_update())
        if target is None:
            _denied(db, request, actor, target_id, "Account not found.", 404)
        grant = db.scalar(select(FinancialSupportGrant).where(
            FinancialSupportGrant.id == grant_id).with_for_update())
        if grant is None:
            _denied(db, request, actor, None)
        is_self = grant.requester_user_id == actor.id
        if is_self and body.self_approval is not True:
            _denied(db, request, actor, grant.target_user_id,
                    "Explicit self-approval must be confirmed.", 422, grant.id)
        if not is_self and body.self_approval:
            _denied(db, request, actor, grant.target_user_id,
                    "Self-approval is only valid for the requesting administrator.", 422, grant.id)
        if grant.status != "pending" or grant.expires_at <= now:
            if grant.status == "pending" and grant.expires_at <= now:
                grant.status = "expired"
                _record(db, request, "support_grant_expired", "success", actor.id, grant.target_user_id, grant.id)
                _commit_or_unavailable(db)
            else:
                _denied(db, request, actor, grant.target_user_id, "The support grant is no longer pending.", 409, grant.id)
            raise HTTPException(409, "The support grant has expired.")
        grant.status, grant.approver_user_id, grant.approved_at = "active", actor.id, now
        if is_self:
            grant.self_approved = True
            _record(db, request, "support_grant_self_approval", "success", actor.id, grant.target_user_id, grant.id)
        _record(db, request, "support_grant_approved", "success", actor.id, grant.target_user_id, grant.id)
        _commit_or_unavailable(db)
        return _response(grant, now)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Support access is temporarily unavailable.", headers={"Retry-After": "1"}) from None


@router.get("/support-grants/{grant_id}", response_model=SupportGrantResponse)
def inspect_support_grant(grant_id: str, request: Request,
                          actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    sid = _superadmin(request, actor, db)
    now = int(time.time())
    try:
        _start_write_lock(db)
        _lock_current_admin_session(db, request, actor, sid)
        grant = db.scalar(select(FinancialSupportGrant).where(
            FinancialSupportGrant.id == grant_id).with_for_update())
        if grant is None or actor.id not in {grant.requester_user_id, grant.approver_user_id}:
            _denied(db, request, actor, grant.target_user_id if grant else None, "Support grant not found.", 404)
        if grant.status in {"pending", "active"} and grant.expires_at <= now:
            grant.status = "expired"
            _record(db, request, "support_grant_expired", "success", actor.id, grant.target_user_id, grant.id)
            _commit_or_unavailable(db)
        _record(db, request, "support_grant_inspected", "success", actor.id, grant.target_user_id, grant.id)
        _commit_or_unavailable(db)
        return _response(grant, now)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Support access is temporarily unavailable.", headers={"Retry-After": "1"}) from None


@router.post("/support-grants/{grant_id}/revoke", response_model=SupportGrantResponse)
def revoke_support_grant(grant_id: str, request: Request,
                         actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    sid = _superadmin(request, actor, db)
    now = int(time.time())
    try:
        _start_write_lock(db)
        _lock_current_admin_session(db, request, actor, sid)
        grant = db.scalar(select(FinancialSupportGrant).where(
            FinancialSupportGrant.id == grant_id).with_for_update())
        if grant is None or actor.id not in {grant.requester_user_id, grant.approver_user_id}:
            _denied(db, request, actor, grant.target_user_id if grant else None, "Support grant not found.", 404)
        if grant.status in {"pending", "active"} and grant.expires_at <= now:
            grant.status = "expired"
            _record(db, request, "support_grant_expired", "success", actor.id, grant.target_user_id, grant.id)
            _record(db, request, "support_grant_revoked", "failure", actor.id, grant.target_user_id, grant.id)
        elif grant.status in {"pending", "active"}:
            grant.status, grant.revoked_at = "revoked", now
            _record(db, request, "support_grant_revoked", "success", actor.id, grant.target_user_id, grant.id)
        else:
            _record(db, request, "support_grant_revoked", "failure" if grant.status == "expired" else "success",
                    actor.id, grant.target_user_id, grant.id)
        _commit_or_unavailable(db)
        return _response(grant, now)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Support access is temporarily unavailable.", headers={"Retry-After": "1"}) from None


def _authorize_financial_read(grant_id, target_id, scope, request, actor, db, totp_code):
    sid = _superadmin(request, actor, db)
    now = int(time.time())
    try:
        _start_write_lock(db)
        apply_read_timeout(db)
        admin = db.scalar(select(User).where(User.id == actor.id).with_for_update()
                           .execution_options(populate_existing=True))
        session = db.scalar(select(AuthSession).where(AuthSession.id == sid, AuthSession.user_id == actor.id,
            AuthSession.revoked_at.is_(None), AuthSession.idle_expires_at > now,
            AuthSession.absolute_expires_at > now).with_for_update()
            .execution_options(populate_existing=True))
        if admin is None or admin.admin_role != "superadmin" or session is None:
            _denied(db, request, actor, target_id, "Administrator access is no longer valid.", 403)
        target = db.scalar(select(User).where(User.id == target_id).with_for_update())
        if target is None:
            _denied(db, request, actor, None, "Account not found.", 404)
        grant = db.scalar(select(FinancialSupportGrant).where(
            FinancialSupportGrant.id == grant_id).with_for_update())
        if grant is None:
            _denied(db, request, actor, target_id, "Support grant is unavailable.", 404)
        if grant.target_user_id != target_id:
            _denied(db, request, actor, grant.target_user_id, "Support grant is unavailable.", 404, grant.id)
        if grant.requester_session_id != sid:
            _denied(db, request, actor, target_id, "Support grant is not valid for this device session.", 403, grant.id)
        if grant.status != "active" or grant.expires_at <= now:
            if grant.status == "active" and grant.expires_at <= now:
                grant.status = "expired"
                _record(db, request, "support_grant_expired", "success", actor.id, target_id, grant.id)
                _commit_or_unavailable(db)
            _denied(db, request, actor, target_id, "Support grant is unavailable or expired.", 403, grant.id)
        if scope not in grant.scopes:
            _denied(db, request, actor, target_id, "This data scope is not included in the grant.", 403, grant.id)
        settings = request.app.state.admin_settings
        if admin.admin_totp_nonce is None or admin.admin_totp_ciphertext is None or admin.admin_totp_key_id != settings.totp_key_id:
            _denied(db, request, actor, target_id, "Administrator verification is unavailable.", 503, grant.id)
        try:
            secret = decrypt_totp_secret(admin.admin_totp_nonce, admin.admin_totp_ciphertext,
                                         admin.id, settings, admin.admin_totp_key_id)
            step = matching_totp_step(secret, totp_code or "", now, admin.admin_totp_last_step)
        except Exception:
            step = None
        if step is None:
            _denied(db, request, actor, target_id, "A new administrator verification code is required.", 403, grant.id)
        admin.admin_totp_last_step = step
        return grant, target
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Support access is temporarily unavailable.", headers={"Retry-After": "1"}) from None


def _finish_financial_read(db, request, actor, target_id, grant_id):
    _record(db, request, "support_financial_read", "success", actor.id, target_id, grant_id)
    _commit_or_unavailable(db)


def _financial_read_unavailable(db):
    db.rollback()
    raise HTTPException(503, "Financial support data is temporarily unavailable.",
                        headers={"Retry-After": "1"}) from None


@router.get("/support-grants/{grant_id}/users/{target_id}/financial-profile",
            response_model=FinancialProfileSupportResponse)
def read_financial_profile(grant_id: str, target_id: Annotated[int, Path(ge=1, le=2147483647)], request: Request,
                           x_admin_totp: str | None = Header(default=None, alias="X-Admin-TOTP"),
                           actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    grant, _ = _authorize_financial_read(grant_id, target_id, "financial_profile", request, actor, db, x_admin_totp)
    try:
        row = db.get(User, target_id)
        result = FinancialProfileSupportResponse(target_user_id=row.id, monthly_income=row.monthly_income,
                                                 fixed_expenses=row.fixed_expenses, currency=row.currency)
    except SQLAlchemyError:
        _financial_read_unavailable(db)
    _finish_financial_read(db, request, actor, target_id, grant.id)
    return result


@router.get("/support-grants/{grant_id}/users/{target_id}/obligations", response_model=SupportObligationPage)
def read_obligations(grant_id: str, target_id: Annotated[int, Path(ge=1, le=2147483647)], request: Request,
                     limit: int = Query(default=50, ge=1, le=READ_PAGE_MAX), offset: int = Query(default=0, ge=0, le=READ_OFFSET_MAX),
                     x_admin_totp: str | None = Header(default=None, alias="X-Admin-TOTP"),
                     actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    grant, _ = _authorize_financial_read(grant_id, target_id, "obligations", request, actor, db, x_admin_totp)
    try:
        rows = db.scalars(select(Obligation).where(
            Obligation.user_id == target_id).order_by(Obligation.id).offset(offset).limit(limit + 1)).all()
        page = rows[:limit]
        result = SupportObligationPage(items=page, offset=offset, limit=limit,
                                       next_offset=offset + limit if len(rows) > limit else None)
    except SQLAlchemyError:
        _financial_read_unavailable(db)
    _finish_financial_read(db, request, actor, target_id, grant.id)
    return result


@router.get("/support-grants/{grant_id}/users/{target_id}/obligations/{obligation_id}/installments",
            response_model=SupportInstallmentPage)
def read_installments(grant_id: str, target_id: Annotated[int, Path(ge=1, le=2147483647)],
                      obligation_id: Annotated[int, Path(ge=1, le=2147483647)], request: Request,
                      limit: int = Query(default=50, ge=1, le=READ_PAGE_MAX), offset: int = Query(default=0, ge=0, le=READ_OFFSET_MAX),
                      x_admin_totp: str | None = Header(default=None, alias="X-Admin-TOTP"),
                      actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    grant, _ = _authorize_financial_read(grant_id, target_id, "installments", request, actor, db, x_admin_totp)
    try:
        obligation = db.scalar(select(Obligation).where(Obligation.id == obligation_id,
                                                        Obligation.user_id == target_id))
        if obligation is None:
            _denied(db, request, actor, target_id, "Obligation not found.", 404, grant.id)
        rows = db.scalars(select(ObligationInstallment).where(
            ObligationInstallment.obligation_id == obligation_id).order_by(
                ObligationInstallment.installment_number).offset(offset).limit(limit + 1)).all()
        result = SupportInstallmentPage(obligation_id=obligation_id, schedule_version=obligation.schedule_version,
                                        items=rows[:limit], offset=offset,
                                        limit=limit, next_offset=offset + limit if len(rows) > limit else None)
    except SQLAlchemyError:
        _financial_read_unavailable(db)
    _finish_financial_read(db, request, actor, target_id, grant.id)
    return result


@router.get("/support-grants/{grant_id}/users/{target_id}/payment-statuses",
            response_model=SupportPaymentStatusPage)
def read_payment_statuses(grant_id: str, target_id: Annotated[int, Path(ge=1, le=2147483647)], request: Request,
                          limit: int = Query(default=50, ge=1, le=READ_PAGE_MAX), offset: int = Query(default=0, ge=0, le=READ_OFFSET_MAX),
                          x_admin_totp: str | None = Header(default=None, alias="X-Admin-TOTP"),
                          actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    grant, _ = _authorize_financial_read(grant_id, target_id, "payment_statuses", request, actor, db, x_admin_totp)
    try:
        rows = db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.user_id == target_id).order_by(
            PaymentOccurrence.due_date, PaymentOccurrence.id).offset(offset).limit(limit + 1)).all()
        items = [SupportPaymentStatus(occurrence_id=row.id, obligation_id=row.obligation_id,
            payment_kind=row.payment_kind, due_date=row.due_date, scheduled_amount=row.scheduled_amount,
            state=row.state, paid_at=row.paid_at) for row in rows[:limit]]
        result = SupportPaymentStatusPage(items=items, offset=offset, limit=limit,
                                          next_offset=offset + limit if len(rows) > limit else None)
    except SQLAlchemyError:
        _financial_read_unavailable(db)
    _finish_financial_read(db, request, actor, target_id, grant.id)
    return result
