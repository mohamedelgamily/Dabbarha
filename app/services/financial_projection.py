"""Attach persisted paid occurrences to forecast inputs without changing schedules."""
from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notifications import PaymentOccurrence
from app.models.obligation import Obligation


def attach_paid_occurrences(
    db: Session,
    user_id: int,
    obligations: Iterable[Obligation],
    start_day: date,
    end_day: date,
) -> None:
    """Annotate loaded obligations with paid payment-kind/date pairs in a window.

    The persisted installment schedule remains authoritative. This state only tells
    forecast consumers which scheduled payments have already been declared paid.
    """
    obligations = list(obligations)
    ids = [obligation.id for obligation in obligations]
    paid_by_obligation: dict[int, set[tuple[str, date]]] = {obligation_id: set() for obligation_id in ids}
    if ids and end_day >= start_day:
        rows = db.scalars(select(PaymentOccurrence).where(
            PaymentOccurrence.user_id == user_id,
            PaymentOccurrence.obligation_id.in_(ids),
            PaymentOccurrence.state == "paid",
            PaymentOccurrence.due_date >= start_day,
            PaymentOccurrence.due_date <= end_day,
        )).all()
        for row in rows:
            paid_by_obligation.setdefault(row.obligation_id, set()).add((row.payment_kind, row.due_date))
    for obligation in obligations:
        obligation.paid_occurrences = paid_by_obligation.get(obligation.id, set())
