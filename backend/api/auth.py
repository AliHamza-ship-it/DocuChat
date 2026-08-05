from fastapi import APIRouter, Depends, HTTPException
from backend.schemas.user import UserRegister, UserLogin
from backend.auth.supabase_auth import AuthService

router = APIRouter()
auth_service = AuthService()

@router.post("/register")
def register(user: UserRegister):
    return auth_service.register_user(user)

@router.post("/login")
def login(user: UserLogin):
    return auth_service.login_user(user)