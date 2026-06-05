from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from pydantic import EmailStr

from app.config import settings


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )

    @staticmethod
    def create_access_token(user_id: str, tenant_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "iat": now,
            "exp": now + timedelta(hours=settings.jwt_expiration_hours),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_access_token(token: str) -> dict:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )

    @staticmethod
    def create_magic_link_token(email: str, tenant_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "email": email,
            "tenant_id": tenant_id,
            "purpose": "magic_link",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    @staticmethod
    def verify_magic_link_token(token: str) -> dict | None:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            if payload.get("purpose") != "magic_link":
                return None
            return payload
        except jwt.PyJWTError:
            return None
