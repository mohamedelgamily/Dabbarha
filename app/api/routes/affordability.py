from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.affordability import AffordabilityResult, ProposedCommitment, evaluate_affordability
from app.core.forecast import month_start
from app.core.forecast import month_index
from app.core.installments import build_installment_schedule
from app.models.obligation import Obligation
from app.models.user import User
from app.schemas.affordability import AffordabilityRequest, AffordabilityResponse

router = APIRouter()


@router.post(
    "",
    response_model=AffordabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate affordability of a proposed commitment",
)
def evaluate_commitment_affordability(
    request: Request,
    body: AffordabilityRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AffordabilityResponse:
    if request.query_params:
        raise HTTPException(
            status_code=422,
            detail="Affordability evaluation does not accept query parameters",
        )

    stmt = select(Obligation).where(Obligation.user_id == current_user.id)
    existing_obligations = list(db.scalars(stmt).all())

    if body.purchase_price is None:
        proposed_commitment = ProposedCommitment(
            amount=body.amount,
            start_date=body.start_date,
            term_months=body.term_months,
        )
        forecast_start = month_start(proposed_commitment.start_date)
        forecast_months = proposed_commitment.term_months
    else:
        manual_amount = body.monthly_installment_amount or body.amount
        try:
            schedule = build_installment_schedule(
                purchase_price=body.purchase_price,
                down_payment_amount=body.down_payment_amount,
                start_date=body.start_date,
                term_months=body.term_months,
                due_day=body.due_day_of_month,
                payment_method=body.payment_method,
                interest_method=body.interest_method,
                nominal_annual_interest_rate=body.nominal_annual_interest_rate,
                manual_monthly_amount=manual_amount,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        proposed_commitment = ProposedCommitment(
            amount=manual_amount or Decimal("0.00"),
            start_date=body.start_date,
            term_months=body.term_months,
            schedule=schedule,
            down_payment_amount=body.down_payment_amount,
            down_payment_date=body.down_payment_date,
            down_payment_paid=body.down_payment_paid,
        )
        dates = [row.due_date for row in schedule]
        if body.down_payment_date is not None and not body.down_payment_paid:
            dates.append(body.down_payment_date)
        forecast_start = month_start(min(dates))
        last_month = month_start(max(dates))
        forecast_months = month_index(last_month) - month_index(forecast_start) + 1
        if forecast_months > 1200:
            raise HTTPException(status_code=422, detail="The complete affordability period cannot exceed 1,200 months.")

    result: AffordabilityResult = evaluate_affordability(
        monthly_income=current_user.monthly_income,
        fixed_expenses=current_user.fixed_expenses,
        existing_obligations=existing_obligations,
        proposed_commitment=proposed_commitment,
        start_month=forecast_start,
        months=forecast_months,
    )

    return AffordabilityResponse(
        classification=result.classification,
        worst_projected_buffer=result.worst_projected_buffer,
        worst_buffer_percentage=result.worst_buffer_percentage,
        worst_month=result.worst_month,
        explanation=result.explanation,
        monthly_results=result.monthly_results,
    )
