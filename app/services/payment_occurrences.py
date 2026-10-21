"""Idempotent payment occurrence materialization and user-declaration transitions."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.notifications import PaymentOccurrence, PaymentOccurrenceEvent
from app.models.obligation import Obligation, ObligationInstallment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class OccurrenceSpec:
    payment_kind: str
    due_date: date
    amount: Decimal
    installment_id: int | None = None
    schedule_version: int = 0


def clamped_due_date(year: int, month: int, due_day: int) -> date:
    return date(year, month, min(due_day, calendar.monthrange(year, month)[1]))


def _month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def expected_occurrences(
    obligation: Obligation, start_day: date, end_day: date, *, include_latest_overdue: bool = False,
) -> list[OccurrenceSpec]:
    """Project dates from authoritative legacy fields or exact stored schedule rows."""
    if end_day < start_day:
        return []
    specs: list[OccurrenceSpec] = []
    candidates: list[OccurrenceSpec] = []
    if obligation.status not in {"active", "late"}:
        return specs
    if obligation.purchase_price is None:
        start_month = _month_index(obligation.start_date)
        lower = max(0, _month_index(start_day) - start_month)
        upper = min(obligation.term_months - 1, _month_index(end_day) - start_month)
        for offset in range(lower, upper + 1):
            index = start_month + offset
            year, month0 = divmod(index, 12)
            due = clamped_due_date(year, month0 + 1, obligation.due_day_of_month)
            candidates.append(OccurrenceSpec("regular", due, obligation.monthly_installment_amount,
                                             schedule_version=0))
        if include_latest_overdue:
            current_offset = _month_index(start_day) - start_month
            if current_offset >= 0:
                for offset in range(min(current_offset, obligation.term_months - 1), -1, -1):
                    index = start_month + offset
                    year, month0 = divmod(index, 12)
                    due = clamped_due_date(year, month0 + 1, obligation.due_day_of_month)
                    if due < start_day:
                        candidates.append(OccurrenceSpec("regular", due, obligation.monthly_installment_amount,
                                                         schedule_version=0))
                        break
    else:
        rows = list(obligation.installments)
        for row in rows:
            if start_day <= row.due_date <= end_day:
                candidates.append(OccurrenceSpec("regular", row.due_date, row.scheduled_amount,
                                                 row.id, obligation.schedule_version))
        if include_latest_overdue:
            earlier = [row for row in rows if row.due_date < start_day]
            if earlier:
                row = max(earlier, key=lambda item: item.due_date)
                candidates.append(OccurrenceSpec("regular", row.due_date, row.scheduled_amount,
                                                 row.id, obligation.schedule_version))

    if obligation.down_payment_amount > 0 and obligation.down_payment_date is not None:
        day = obligation.down_payment_date
        if (start_day <= day <= end_day) or (include_latest_overdue and day < start_day):
            candidates.append(OccurrenceSpec("down_payment", day, obligation.down_payment_amount,
                                             schedule_version=obligation.schedule_version))
    for spec in candidates:
        if spec.due_date not in {item.due_date for item in specs} or spec.payment_kind == "down_payment":
            specs.append(spec)
    # Keep only the latest overdue regular payment, even if a date range included older months.
    if include_latest_overdue:
        overdue = [spec for spec in specs if spec.payment_kind == "regular" and spec.due_date < start_day]
        if len(overdue) > 1:
            keep = max(overdue, key=lambda item: item.due_date)
            specs = [spec for spec in specs if spec.payment_kind != "regular" or spec.due_date >= start_day or spec is keep]
    return sorted(specs, key=lambda item: (item.due_date, item.payment_kind))


def materialize_occurrence(db: Session, obligation: Obligation, spec: OccurrenceSpec) -> PaymentOccurrence:
    key = f"{spec.payment_kind}:{spec.due_date.isoformat()}"
    values = {
        "user_id": obligation.user_id,
        "obligation_id": obligation.id,
        "installment_id": spec.installment_id,
        "occurrence_key": key,
        "payment_kind": spec.payment_kind,
        "due_date": spec.due_date,
        "scheduled_amount": spec.amount,
        "schedule_version": spec.schedule_version,
        "state": "paid" if spec.payment_kind == "down_payment" and obligation.down_payment_paid else "unpaid",
        "paid_at": utc_now() if spec.payment_kind == "down_payment" and obligation.down_payment_paid else None,
    }
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(pg_insert(PaymentOccurrence).values(**values).on_conflict_do_nothing(
            constraint="uq_payment_occurrence_key"))
    elif bind.dialect.name == "sqlite":
        db.execute(sqlite_insert(PaymentOccurrence).values(**values).on_conflict_do_nothing(
            index_elements=["obligation_id", "occurrence_key"]))
    else:
        if db.scalar(select(PaymentOccurrence.id).where(
            PaymentOccurrence.obligation_id == obligation.id,
            PaymentOccurrence.occurrence_key == key,
        )) is None:
            db.add(PaymentOccurrence(**values))
            db.flush()
    row = db.scalar(select(PaymentOccurrence).where(
        PaymentOccurrence.obligation_id == obligation.id,
        PaymentOccurrence.occurrence_key == key,
    ).with_for_update())
    if row is None:
        raise RuntimeError("Payment occurrence could not be materialized.")
    was_superseded = row.state == "superseded"
    if row.state != "paid":
        row.installment_id = spec.installment_id
        row.due_date = spec.due_date
        row.scheduled_amount = spec.amount
        row.schedule_version = spec.schedule_version
        if was_superseded:
            row.state = "unpaid"
            row.paid_at = None
            row.reminder_epoch += 1
        if spec.payment_kind == "down_payment" and obligation.down_payment_paid:
            row.state = "paid"
            row.paid_at = row.paid_at or utc_now()
    if spec.payment_kind == "down_payment" and obligation.down_payment_paid:
        prior_event = db.scalar(select(PaymentOccurrenceEvent.id).where(
            PaymentOccurrenceEvent.occurrence_id == row.id,
            PaymentOccurrenceEvent.action == "marked_paid",
        ).limit(1))
        if prior_event is None:
            db.add(PaymentOccurrenceEvent(occurrence_id=row.id, user_id=obligation.user_id, action="marked_paid"))
    return row
