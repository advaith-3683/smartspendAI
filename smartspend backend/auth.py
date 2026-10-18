"""Opaque, revocable sessions. No identity or bearer secrets in browser storage."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from database import Base, get_db
import models

COOKIE = "smartspend_session"
SESSION_HOURS = 24
SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
if os.getenv("APP_ENV") == "production" and not SECURE:
    raise RuntimeError("Production authentication requires COOKIE_SECURE=true")
if SAMESITE not in {"lax", "strict", "none"} or (SAMESITE == "none" and not SECURE):
    raise RuntimeError("Cross-site cookies require COOKIE_SECURE=true")

class Credential(Base):
    __tablename__ = "credentials"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)

class Login(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value

def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return salt.hex() + ":" + value.hex()

def password_matches(password, stored):
    salt, expected = stored.split(":")
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return hmac.compare_digest(actual.hex(), expected)

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def issue_session(db, response, user_id):
    token = secrets.token_urlsafe(32)
    db.query(AuthSession).filter(AuthSession.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)).delete()
    db.add(AuthSession(token_hash=token_hash(token), user_id=user_id,
                       expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=SESSION_HOURS)))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True,
                        secure=SECURE, samesite=SAMESITE, path="/")

def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE)
    session = db.get(AuthSession, token_hash(token)) if token else None
    if not session or session.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(401, "Please log in")
    user = db.get(models.User, session.user_id)
    if not user:
        raise HTTPException(401, "Please log in")
    return user

async def authorize(request: Request, user=Depends(current_user), db=Depends(get_db)):
    """Compatibility IDs are checked against the session, never used as credentials."""
    request.state.user_id = user.id
    if "user_id" in request.path_params and int(request.path_params["user_id"]) != user.id:
        raise HTTPException(404, "Resource not found")
    for key, model in (("bill_id", models.Bill), ("transaction_id", models.Transaction)):
        if key in request.path_params:
            item = db.get(model, int(request.path_params[key]))
            if not item or item.user_id != user.id:
                raise HTTPException(404, "Resource not found")
    if request.headers.get("content-type", "").startswith("application/json"):
        import json
        raw = await request.body()
        try:
            body = json.loads(raw) if raw else {}
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Invalid JSON body")
        if isinstance(body, dict) and "user_id" in body and body["user_id"] != user.id:
            raise HTTPException(403, "User does not match authenticated session")
    for key, low, high in (("year", 1900, 2200), ("month", 1, 12)):
        if key in request.query_params:
            try:
                value = int(request.query_params[key])
                assert low <= value <= high
            except (ValueError, AssertionError):
                raise HTTPException(422, f"Invalid {key}")
    if ("year" in request.query_params) != ("month" in request.query_params):
        raise HTTPException(422, "Supply both year and month")
