from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
