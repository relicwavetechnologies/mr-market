from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_session
from app.security.hash import hash_password, verify_password
from app.security.tokens import TokenDecodeError, decode, issue_access, issue_refresh, require_type

router = APIRouter(prefix="/api/users", tags=["users"])


VALID_RISK_PROFILES = {"conservative", "balanced", "aggressive"}


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    risk_profile: str = "balanced"
    created_at: datetime
    last_login_at: datetime | None = None

    @classmethod
    def from_model(cls, user: User) -> "UserOut":
        return cls(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            risk_profile=user.risk_profile or "balanced",
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class AuthResponse(BaseModel):
    user: UserOut
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SignupPayload(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(..., min_length=1, max_length=120)


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class RefreshPayload(BaseModel):
    refresh_token: str = Field(..., min_length=8)


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupPayload, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    email = payload.email.lower()
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists") from e

    await session.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginPayload, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    email = payload.email.lower()
    user = await _get_user_by_email(email, session=session)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)
    return _auth_response(user)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshPayload, session: AsyncSession = Depends(get_session)) -> RefreshResponse:
    try:
        token_payload = decode(payload.refresh_token)
        require_type(token_payload, "refresh")
        user_id = uuid.UUID(str(token_payload["sub"]))
    except (KeyError, TokenDecodeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token") from e

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return RefreshResponse(access_token=issue_access(str(user.id)))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_model(current_user)


class RiskProfileOut(BaseModel):
    risk_profile: str


class RiskProfilePayload(BaseModel):
    risk_profile: str = Field(..., description="One of: conservative, balanced, aggressive")


@router.get("/me/risk-profile", response_model=RiskProfileOut)
async def get_risk_profile(current_user: User = Depends(get_current_user)) -> RiskProfileOut:
    return RiskProfileOut(risk_profile=current_user.risk_profile or "balanced")


@router.put("/me/risk-profile", response_model=RiskProfileOut)
async def set_risk_profile(
    payload: RiskProfilePayload,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RiskProfileOut:
    value = payload.risk_profile.lower().strip()
    if value not in VALID_RISK_PROFILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"risk_profile must be one of: {', '.join(sorted(VALID_RISK_PROFILES))}",
        )
    current_user.risk_profile = value
    await session.commit()
    await session.refresh(current_user)
    return RiskProfileOut(risk_profile=current_user.risk_profile)


@router.post("/logout")
async def logout(_: User = Depends(get_current_user)) -> dict[str, bool]:
    return {"ok": True}


async def _get_user_by_email(email: str, *, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


def _auth_response(user: User) -> AuthResponse:
    sub = str(user.id)
    return AuthResponse(
        user=UserOut.from_model(user),
        access_token=issue_access(sub),
        refresh_token=issue_refresh(sub),
    )
