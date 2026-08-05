from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client
from backend.database.supabase_client import get_supabase_client
from backend.schemas.user import UserRegister, UserLogin

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Middleware to verify JWT token and get current user."""
    supabase: Client = get_supabase_client()
    try:
        # Verify the JWT with Supabase Auth
        user = supabase.auth.get_user(credentials.credentials)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

class AuthService:
    def __init__(self):
        self.supabase = get_supabase_client()

    def register_user(self, user_data: UserRegister):
        try:
            # Register user with Supabase Auth
            response = self.supabase.auth.sign_up({
                "email": user_data.email,
                "password": user_data.password,
                "options": {
                    "data": {
                        "name": user_data.name,
                        "age": user_data.age,
                        "country": user_data.country
                    }
                }
            })
            return {"message": "Registration successful. Please check your email to verify your account."}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def login_user(self, user_data: UserLogin):
        try:
            response = self.supabase.auth.sign_in_with_password({
                "email": user_data.email,
                "password": user_data.password
            })
            return {
                "access_token": response.session.access_token,
                "token_type": "bearer",
                "user": response.user.user_metadata
            }
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid email or password. Verify your email if you haven't.")