from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import login_rate_limit
from app.models import Role, User
from app.schemas import RoleUpdate, Token, UserCreate, UserOut
from app.security import Admin, CurrentUser, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Checked against when the email is unknown so both paths cost one bcrypt verify,
# which keeps response time from revealing which emails are registered.
_DUMMY_HASH = hash_password("timing-equaliser")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
    # The first account bootstraps the install as admin; everyone after starts as viewer.
    is_first = db.scalar(select(func.count()).select_from(User)) == 0
    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        role=Role.admin if is_first else Role.viewer,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return user


@router.post("/login", response_model=Token, dependencies=[Depends(login_rate_limit)])
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    valid = verify_password(form.password, user.hashed_password if user else _DUMMY_HASH)
    if user is None or not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: int, body: RoleUpdate, admin: Admin, db: Annotated[Session, Depends(get_db)]) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id and body.role != Role.admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins cannot demote themselves")
    user.role = body.role
    db.commit()
    return user
