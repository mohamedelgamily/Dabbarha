from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.affordability import AffordabilityResult, ProposedCommitment, evaluate_affordability
from app.core.forecast import month_start
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

    proposed_commitment = ProposedCommitment(
        amount=body.amount,
        start_date=body.start_date,
        term_months=body.term_months,
    )

    result: AffordabilityResult = evaluate_affordability(
        monthly_income=current_user.monthly_income,
        fixed_expenses=current_user.fixed_expenses,
        existing_obligations=existing_obligations,
        proposed_commitment=proposed_commitment,
        start_month=month_start(proposed_commitment.start_date),
        months=proposed_commitment.term_months,
    )

    return AffordabilityResponse(
        classification=result.classification,
        worst_projected_buffer=result.worst_projected_buffer,
        worst_buffer_percentage=result.worst_buffer_percentage,
        worst_month=result.worst_month,
        explanation=result.explanation,
        monthly_results=result.monthly_results,
    )
