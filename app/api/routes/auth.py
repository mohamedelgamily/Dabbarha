from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import DUMMY_PASSWORD_HASH, create_access_token, hash_password, verify_password
from app.core.api_security import source_ip
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
    request: Request,
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

    with request.app.state.security.password_slot():
        encoded_password = hash_password(user_in.password)
    user = User(
        name=user_in.name.strip(),
        email=normalized_email,
        password_hash=encoded_password,
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
    request: Request,
    db: Session = Depends(get_db),
) -> Token:
    normalized_email = credentials.email.strip().lower()

    stmt = select(User).where(User.email == normalized_email)
    user = db.scalar(stmt)

    runtime = request.app.state.security
    reservation = runtime.login_reserve(normalized_email, source_ip(request.scope))
    try:
        with runtime.password_slot():
            verified = verify_password(credentials.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    except Exception:
        runtime.limiter.release(reservation)
        raise
    if user is None or not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    runtime.limiter.release(reservation)
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

    try:
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    except Exception:
        db.rollback()
        raise

    return current_user
