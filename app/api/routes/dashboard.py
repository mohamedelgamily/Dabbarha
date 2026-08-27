from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.forecast import build_forecast, month_start
from app.models.obligation import Obligation
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryResponse

router = APIRouter()


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard summary",
)
def get_dashboard_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    if request.query_params:
        raise HTTPException(
            status_code=422,
            detail="Dashboard summary does not accept query parameters",
        )

    stmt = select(Obligation).where(Obligation.user_id == current_user.id)
    obligations = list(db.scalars(stmt).all())
    current_month = month_start(date.today())

    forecast = build_forecast(
        monthly_income=current_user.monthly_income,
        fixed_expenses=current_user.fixed_expenses,
        obligations=obligations,
        start_month=current_month,
        months=1,
    )
    current_month_forecast = forecast[0]

    return DashboardSummaryResponse(
        monthly_income=current_user.monthly_income,
        fixed_expenses=current_user.fixed_expenses,
        current_month_obligation_payments=current_month_forecast.obligation_payments,
        current_month_projected_buffer=current_month_forecast.projected_buffer,
        has_current_month_negative_buffer=current_month_forecast.has_negative_buffer,
        active_obligations_count=sum(
            1 for obligation in obligations if obligation.status in {"active", "late"}
        ),
    )
