"""Verifies Supabase Auth access tokens on protected routes.

Sign-up/sign-in/session refresh all happen on the frontend directly against Supabase
(via supabase-js) - this backend never sees a password, it only verifies the JWT
Supabase already issued. Supabase signs access tokens with a per-project asymmetric
key (ES256) rather than a shared secret, so verification means fetching the project's
public JWKS and checking the signature against that - no local `users` table, since
Supabase's `auth.users` is the source of truth and we just trust the `sub` claim as the
user id.
"""

import uuid
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

from app.core.config import get_settings


@lru_cache
def _jwk_client() -> jwt.PyJWKClient:
    settings = get_settings()
    return jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


def get_current_user_id(authorization: str | None = Header(default=None)) -> uuid.UUID:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
