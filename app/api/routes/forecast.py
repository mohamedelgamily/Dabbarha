from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.forecast import build_forecast
from app.models.obligation import Obligation
from app.models.user import User
from app.schemas.forecast import ForecastResponse

router = APIRouter()


@router.get(
    "",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Get monthly cash-flow forecast",
)
def get_forecast(
    request: Request,
    start_month: date = Query(...),
    months: int = Query(..., gt=0, le=60),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    allowed_query_params = {"start_month", "months"}
    extra_query_params = set(request.query_params.keys()) - allowed_query_params
    if extra_query_params:
        raise HTTPException(
            status_code=422,
            detail="Only start_month and months query parameters are accepted",
        )

    stmt = select(Obligation).where(Obligation.user_id == current_user.id)
    obligations = list(db.scalars(stmt).all())

    rows = build_forecast(
        monthly_income=current_user.monthly_income,
        fixed_expenses=current_user.fixed_expenses,
        obligations=obligations,
        start_month=start_month,
        months=months,
    )

    return ForecastResponse(rows=rows)
