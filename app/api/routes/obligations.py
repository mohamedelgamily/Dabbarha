from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_db
from app.core.forecast import add_months
from app.core.installments import build_installment_schedule
from app.models.obligation import Obligation, ObligationInstallment
from app.models.notifications import Notification, PaymentOccurrence, PaymentOccurrenceEvent
from app.models.user import User
from app.schemas.obligation import (
    ObligationCreate,
    ObligationResponse,
    ObligationUpdate,
    InstallmentPlanCreate,
    InstallmentPlanConversion,
    InstallmentPlanUpdate,
    InstallmentScheduleResponse,
)
from app.schemas.notifications import PaymentOccurrenceList, PaymentOccurrenceResponse
from app.core.notification_copy import COPY_VERSION, render_copy
from app.services.notifications import cancel_occurrence_notifications, get_preferences, invalidate_obligation_schedule
from app.services.payment_occurrences import expected_occurrences, materialize_occurrence

router = APIRouter()


def _plan_rows(plan: InstallmentPlanCreate):
    try:
        return build_installment_schedule(
            purchase_price=plan.purchase_price,
            down_payment_amount=plan.down_payment_amount,
            start_date=plan.start_date,
            term_months=plan.term_months,
            due_day=plan.due_day_of_month,
            payment_method=plan.payment_method,
            interest_method=plan.interest_method,
            nominal_annual_interest_rate=plan.nominal_annual_interest_rate,
            manual_monthly_amount=plan.monthly_installment_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _persist_plan_fields(obligation: Obligation, plan: InstallmentPlanCreate, rows, *, version: int) -> None:
    # total_amount remains a compatibility snapshot; purchase_price is authoritative for plan math.
    obligation.total_amount = plan.purchase_price
    obligation.monthly_installment_amount = rows[0].amount
    obligation.provider = plan.provider.strip()
    obligation.item_name = plan.item_name.strip()
    obligation.category = plan.category.strip()
    obligation.purchase_price = plan.purchase_price
    obligation.payment_method = plan.payment_method
    obligation.interest_method = plan.interest_method
    obligation.nominal_annual_interest_rate = plan.nominal_annual_interest_rate
    obligation.down_payment_amount = plan.down_payment_amount
    obligation.down_payment_date = plan.down_payment_date
    obligation.down_payment_paid = plan.down_payment_paid
    obligation.start_date = plan.start_date
    obligation.term_months = plan.term_months
    obligation.due_day_of_month = plan.due_day_of_month
    obligation.status = plan.status
    obligation.schedule_version = version
    obligation.installments = [
        ObligationInstallment(
            installment_number=row.number,
            due_date=row.due_date,
            scheduled_amount=row.amount,
            principal_amount=row.principal,
            interest_amount=row.interest,
        )
        for row in rows
    ]


def _require_confirmation(confirm: bool) -> None:
    if not confirm:
        raise HTTPException(status_code=422, detail="Review the proposed plan and confirm conversion.")


@router.post(
    "/installment-plans",
    response_model=ObligationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an explicitly calculated or manually entered installment plan",
)
def create_installment_plan(
    plan: InstallmentPlanCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    rows = _plan_rows(plan)
    obligation = Obligation(
        user_id=current_user.id,
        provider=plan.provider,
        item_name=plan.item_name,
        category=plan.category,
        total_amount=plan.purchase_price,
        monthly_installment_amount=rows[0].amount,
        start_date=plan.start_date,
        term_months=plan.term_months,
        due_day_of_month=plan.due_day_of_month,
        status=plan.status,
        source="manual_entry",
    )
    _persist_plan_fields(obligation, plan, rows, version=1)
    try:
        db.add(obligation)
        db.commit()
        db.refresh(obligation)
    except Exception:
        db.rollback()
        raise
    return obligation


@router.get("/{id}/payment-occurrences", response_model=PaymentOccurrenceList,
            summary="List payment occurrences for one owned obligation")
def list_payment_occurrences(
    id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    start_date: date | None = None,
    months: int = 6,
) -> PaymentOccurrenceList:
    if not request.app.state.notification_settings.enabled:
        raise HTTPException(503, "Payment tracking is temporarily unavailable.")
    if not 1 <= months <= 12:
        raise HTTPException(422, "Choose a range from 1 to 12 months.")
    obligation = db.scalar(select(Obligation).options(selectinload(Obligation.installments)).where(
        Obligation.id == id, Obligation.user_id == current_user.id,
    ))
    if obligation is None:
        raise HTTPException(404, "Obligation not found")
    start = start_date or date.today().replace(day=1)
    end = add_months(date(start.year, start.month, 1), months) - timedelta(days=1)
    for spec in expected_occurrences(obligation, start, end, include_latest_overdue=True):
        materialize_occurrence(db, obligation, spec)
    rows = list(db.scalars(select(PaymentOccurrence).where(
        PaymentOccurrence.obligation_id == id,
        PaymentOccurrence.user_id == current_user.id,
        PaymentOccurrence.due_date <= end,
        PaymentOccurrence.due_date >= start - timedelta(days=366),
    ).order_by(PaymentOccurrence.due_date.desc(), PaymentOccurrence.id.desc())).all())
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return PaymentOccurrenceList(rows=rows)


def _owned_occurrence(db: Session, obligation_id: int, occurrence_id: int, user_id: int):
    row = db.scalar(select(PaymentOccurrence).where(
        PaymentOccurrence.id == occurrence_id,
        PaymentOccurrence.obligation_id == obligation_id,
        PaymentOccurrence.user_id == user_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Payment occurrence not found")
    return row


@router.post("/{id}/payment-occurrences/{occurrence_id}/mark-paid",
            response_model=PaymentOccurrenceResponse,
            summary="Record the user's declaration that a payment was paid")
def mark_occurrence_paid(
    id: int,
    occurrence_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentOccurrence:
    if not request.app.state.notification_settings.enabled:
        raise HTTPException(503, "Payment tracking is temporarily unavailable.")
    obligation = db.scalar(select(Obligation).where(
        Obligation.id == id, Obligation.user_id == current_user.id,
    ).with_for_update())
    if obligation is None:
        raise HTTPException(404, "Obligation not found")
    occurrence = _owned_occurrence(db, id, occurrence_id, current_user.id)
    if occurrence.state == "superseded":
        raise HTTPException(409, "This payment schedule changed. Reload the current schedule.")
    if occurrence.state == "paid":
        return occurrence
    occurrence.state = "paid"
    occurrence.paid_at = datetime.now(timezone.utc)
    db.add(PaymentOccurrenceEvent(occurrence_id=occurrence.id, user_id=current_user.id, action="marked_paid"))
    if occurrence.payment_kind == "down_payment":
        obligation.down_payment_paid = True
    cancel_occurrence_notifications(db, [occurrence.id])
    pref = get_preferences(db, current_user.id, create=False)
    if pref is not None and pref.reminders_enabled and "payment_completed" in pref.categories:
        title, body = render_copy("payment_completed", pref.language, pref.privacy_mode,
                                  item_name=obligation.item_name, amount=occurrence.scheduled_amount)
        db.add(Notification(
            user_id=current_user.id, obligation_id=id, occurrence_id=occurrence.id,
            notification_type="payment_completed",
            deduplication_key=f"payment-completed:{occurrence.id}:{occurrence.reminder_epoch}:{int(occurrence.paid_at.timestamp())}",
            scheduled_at=occurrence.paid_at, title=title, body=body,
            copy_version=COPY_VERSION, route="obligation_detail", delivery_state="queued",
        ))
    try:
        db.commit()
        db.refresh(occurrence)
    except Exception:
        db.rollback()
        raise
    return occurrence


@router.post("/{id}/payment-occurrences/{occurrence_id}/undo-paid",
            response_model=PaymentOccurrenceResponse,
            summary="Undo an accidental user payment declaration")
def undo_occurrence_paid(
    id: int,
    occurrence_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentOccurrence:
    if not request.app.state.notification_settings.enabled:
        raise HTTPException(503, "Payment tracking is temporarily unavailable.")
    obligation = db.scalar(select(Obligation).where(
        Obligation.id == id, Obligation.user_id == current_user.id,
    ).with_for_update())
    if obligation is None:
        raise HTTPException(404, "Obligation not found")
    occurrence = _owned_occurrence(db, id, occurrence_id, current_user.id)
    if occurrence.state == "superseded":
        raise HTTPException(409, "This payment schedule changed. Reload the current schedule.")
    if occurrence.state == "unpaid":
        return occurrence
    occurrence.state = "unpaid"
    occurrence.paid_at = None
    occurrence.reminder_epoch += 1
    db.add(PaymentOccurrenceEvent(occurrence_id=occurrence.id, user_id=current_user.id, action="undone"))
    if occurrence.payment_kind == "down_payment":
        obligation.down_payment_paid = False
    cancel_occurrence_notifications(db, [occurrence.id])
    db.execute(update(Notification).where(
        Notification.occurrence_id == occurrence.id,
        Notification.notification_type == "payment_completed",
        Notification.delivery_state.in_(["queued", "sending"]),
    ).values(delivery_state="cancelled"))
    try:
        db.commit()
        db.refresh(occurrence)
    except Exception:
        db.rollback()
        raise
    return occurrence


@router.post(
    "/{id}/convert-to-installment-plan",
    response_model=ObligationResponse,
    summary="Convert a legacy obligation after reviewing and confirming its plan",
)
def convert_obligation_to_plan(
    id: int,
    plan: InstallmentPlanConversion,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    _require_confirmation(plan.confirm_conversion)
    obligation = db.scalar(
        select(Obligation).where(Obligation.id == id, Obligation.user_id == current_user.id)
    )
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    if obligation.purchase_price is not None:
        raise HTTPException(status_code=409, detail="This obligation already has an installment plan.")
    conversion_plan = plan.model_copy(update={"status": plan.status or obligation.status})
    rows = _plan_rows(conversion_plan)
    try:
        changed = db.execute(
            update(Obligation)
            .where(
                Obligation.id == id,
                Obligation.user_id == current_user.id,
                Obligation.purchase_price.is_(None),
                Obligation.schedule_version == 0,
            )
            .values(schedule_version=1)
        ).rowcount
        if changed != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="The obligation changed. Reload it before confirming conversion.")
        _persist_plan_fields(obligation, conversion_plan, rows, version=1)
        db.add(obligation)
        db.commit()
        db.refresh(obligation)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    return obligation


@router.put(
    "/{id}/installment-plan",
    response_model=ObligationResponse,
    summary="Update an installment plan using optimistic schedule versioning",
)
def update_installment_plan(
    id: int,
    plan: InstallmentPlanUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    obligation = db.scalar(
        select(Obligation).where(Obligation.id == id, Obligation.user_id == current_user.id)
    )
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    if obligation.purchase_price is None:
        raise HTTPException(status_code=409, detail="Explicitly convert this legacy obligation before editing a plan.")
    if obligation.schedule_version != plan.schedule_version:
        raise HTTPException(status_code=409, detail="The plan changed. Reload it before saving your edits.")
    if plan.down_payment_paid != obligation.down_payment_paid:
        raise HTTPException(
            status_code=409,
            detail="Use the payment occurrence's Mark as paid or Undo paid action to change payment status.",
        )
    if obligation.down_payment_paid and (
        plan.down_payment_amount != obligation.down_payment_amount
        or plan.down_payment_date != obligation.down_payment_date
    ):
        raise HTTPException(
            status_code=409,
            detail="Undo the recorded down payment before changing its amount or date.",
        )
    updated_plan = plan.model_copy(update={"status": plan.status or obligation.status})
    rows = _plan_rows(updated_plan)
    next_version = plan.schedule_version + 1
    try:
        changed = db.execute(
            update(Obligation)
            .where(
                Obligation.id == id,
                Obligation.user_id == current_user.id,
                Obligation.schedule_version == plan.schedule_version,
            )
            .values(schedule_version=next_version)
        ).rowcount
        if changed != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="The plan changed. Reload it before saving your edits.")
        invalidate_obligation_schedule(db, obligation)
        # Refresh after the compare-and-swap update, then replace rows in this transaction.
        db.refresh(obligation)
        obligation.installments = []
        db.flush()
        _persist_plan_fields(obligation, updated_plan, rows, version=next_version)
        db.add(obligation)
        db.commit()
        db.refresh(obligation)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    return obligation


@router.get(
    "/{id}/installments",
    response_model=InstallmentScheduleResponse,
    summary="Get the exact installment schedule",
)
def get_installment_schedule(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InstallmentScheduleResponse:
    obligation = db.scalar(
        select(Obligation).where(Obligation.id == id, Obligation.user_id == current_user.id)
    )
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    if obligation.purchase_price is None:
        raise HTTPException(status_code=404, detail="Installment schedule not found")
    return InstallmentScheduleResponse(
        obligation_id=id,
        schedule_version=obligation.schedule_version,
        installments=list(obligation.installments),
    )


@router.post(
    "",
    response_model=ObligationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new obligation",
)
def create_obligation(
    obligation_in: ObligationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    obligation = Obligation(
        user_id=current_user.id,
        provider=obligation_in.provider.strip(),
        item_name=obligation_in.item_name.strip(),
        category=obligation_in.category.strip(),
        total_amount=obligation_in.total_amount,
        monthly_installment_amount=obligation_in.monthly_installment_amount,
        start_date=obligation_in.start_date,
        term_months=obligation_in.term_months,
        due_day_of_month=obligation_in.due_day_of_month,
        status=obligation_in.status,
        source=obligation_in.source,
    )

    try:
        db.add(obligation)
        db.commit()
        db.refresh(obligation)
    except Exception:
        db.rollback()
        raise

    return obligation


@router.get(
    "",
    response_model=list[ObligationResponse],
    status_code=status.HTTP_200_OK,
    summary="List obligations for the authenticated user",
)
def list_obligations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Obligation]:
    stmt = select(Obligation).where(Obligation.user_id == current_user.id)
    obligations = db.scalars(stmt).all()
    return list(obligations)


@router.get(
    "/{id}",
    response_model=ObligationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a specific obligation by ID",
)
def get_obligation(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    stmt = select(Obligation).where(
        Obligation.id == id,
        Obligation.user_id == current_user.id,
    )
    obligation = db.scalar(stmt)
    if obligation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obligation not found",
        )
    return obligation

@router.put(
    "/{id}",
    response_model=ObligationResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an obligation",
)
def update_obligation(
    id: int,
    obligation_in: ObligationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Obligation:
    stmt = select(Obligation).where(
        Obligation.id == id,
        Obligation.user_id == current_user.id,
    )

    obligation = db.scalar(stmt)

    if obligation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obligation not found",
        )

    update_data = obligation_in.model_dump(exclude_unset=True)

    plan_calculation_fields = {"total_amount", "monthly_installment_amount", "start_date", "term_months", "due_day_of_month"}
    if obligation.purchase_price is not None and plan_calculation_fields.intersection(update_data):
        raise HTTPException(
            status_code=409,
            detail="Use the versioned installment-plan endpoint to change a scheduled plan.",
        )

    # Validate before mutating the ORM object, including fields omitted by the client.
    merged = {field: getattr(obligation, field) for field in ObligationCreate.model_fields}
    merged.update(update_data)
    try:
        ObligationCreate.model_validate(merged)
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        for error in errors:
            error["loc"] = ("body", *error["loc"])
        raise RequestValidationError(errors) from None

    for field, value in update_data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(obligation, field, value)

    try:
        plan_fields = {"total_amount", "monthly_installment_amount", "start_date", "term_months", "due_day_of_month"}
        terminal = obligation.status in {"completed", "defaulted"}
        if plan_fields.intersection(update_data) or terminal:
            invalidate_obligation_schedule(db, obligation, supersede=True)
        elif update_data:
            invalidate_obligation_schedule(db, obligation, supersede=False)
        db.commit()
        db.refresh(obligation)
    except Exception:
        db.rollback()
        raise

    return obligation


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an obligation",
)
def delete_obligation(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    stmt = select(Obligation).where(
        Obligation.id == id,
        Obligation.user_id == current_user.id,
    )

    obligation = db.scalar(stmt)

    if obligation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obligation not found",
        )

    try:
        invalidate_obligation_schedule(db, obligation, remove=True)
        db.delete(obligation)
        db.commit()
    except Exception:
        db.rollback()
        raise
