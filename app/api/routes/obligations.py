from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.obligation import Obligation
from app.models.user import User
from app.schemas.obligation import ObligationCreate, ObligationResponse

router = APIRouter()


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
