from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    organisation_name: str = Field(min_length=1, max_length=255)
    # Deprecated: ignored. Joining an existing org requires an invite token
    # (POST /auth/accept-invite). Kept optional so old clients do not 422.
    org_id: str | None = None
    promo_code: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    org_id: str
    user_id: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    password: str = Field(min_length=6, max_length=128)

