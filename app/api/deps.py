from collections.abc import Generator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject: str | None = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = int(subject)
        if not -9223372036854775808 <= user_id <= 9223372036854775807:
            raise credentials_exception
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    request.app.state.sessions.authorize(db, payload, token)
    try:
        user = db.get(User, user_id)
    except SQLAlchemyError:
        from app.services.sessions import unavailable
        raise unavailable() from None
    if user is None:
        raise credentials_exception

    request.state.auth_payload = payload
    request.app.state.security.financial(request, user.id)
    return user
