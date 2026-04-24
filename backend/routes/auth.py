from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from dependencies import get_current_user
from services.auth_service import create_token, get_user, login_user, register_user
from services.plan_service import get_user_plan_info

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    token: str
    plan: str
    monthly_limit: int
    monthly_used: int


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest) -> AuthResponse:
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    try:
        user_id, token = register_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    user = get_user(user_id)
    info = get_user_plan_info(user_id, user["plan"])
    return AuthResponse(
        user_id=user_id,
        email=user["email"],
        token=token,
        plan=user["plan"],
        monthly_limit=info["monthly_limit"],
        monthly_used=info["monthly_used"],
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest) -> AuthResponse:
    try:
        user_id, token = login_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    user = get_user(user_id)
    info = get_user_plan_info(user_id, user["plan"])
    return AuthResponse(
        user_id=user_id,
        email=user["email"],
        token=token,
        plan=user["plan"],
        monthly_limit=info["monthly_limit"],
        monthly_used=info["monthly_used"],
    )


@router.get("/me", response_model=AuthResponse)
async def me(user: dict = Depends(get_current_user)) -> AuthResponse:
    info = get_user_plan_info(user["id"], user["plan"])
    # Refresh token on /me so long-running sessions stay alive
    token = create_token(user["id"])
    return AuthResponse(
        user_id=user["id"],
        email=user["email"],
        token=token,
        plan=user["plan"],
        monthly_limit=info["monthly_limit"],
        monthly_used=info["monthly_used"],
    )
