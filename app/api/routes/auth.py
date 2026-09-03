from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserLogin, UserResponse, UserUpdate

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    normalized_email = user_in.email.strip().lower()

    stmt = select(User).where(User.email == normalized_email)
    existing_user = db.scalar(stmt)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = User(
        name=user_in.name.strip(),
        email=normalized_email,
        password_hash=hash_password(user_in.password),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )
    except Exception:
        db.rollback()
        raise

    return user


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and return access token",
)
def login(
    credentials: UserLogin,
    db: Session = Depends(get_db),
) -> Token:
    normalized_email = credentials.email.strip().lower()

    stmt = select(User).where(User.email == normalized_email)
    user = db.scalar(stmt)

    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user financial profile",
)
def update_current_user_profile(
    profile_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    update_data = profile_in.model_dump(exclude_unset=True)

    if "monthly_income" in update_data:
        current_user.monthly_income = update_data["monthly_income"]

    if "fixed_expenses" in update_data:
        current_user.fixed_expenses = update_data["fixed_expenses"]

    if "currency" in update_data:
        current_user.currency = update_data["currency"].strip().upper()

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return current_user
