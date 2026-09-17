"""Verifies Supabase Auth access tokens on protected routes.

Sign-up/sign-in/session refresh all happen on the frontend directly against Supabase
(via supabase-js) - this backend never sees a password, it only verifies the JWT
Supabase already issued, using the project's shared JWT secret (HS256). No local
`users` table: Supabase's `auth.users` is the source of truth, we just trust the `sub`
claim as the user id.
"""

import uuid

import jwt
from fastapi import Header, HTTPException

from app.core.config import get_settings


def get_current_user_id(authorization: str | None = Header(default=None)) -> uuid.UUID:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ")
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
