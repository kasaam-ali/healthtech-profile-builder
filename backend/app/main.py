from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import schemas
from .config import settings
from .db import Base, engine, get_db
from .deps import current_admin, current_user
from .models import User
from .security import (create_access_token, create_refresh_token, decode_token,
                       hash_password, verify_password)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="HealthTech Profile Builder - Week 1")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                   https_only=False, same_site="lax", max_age=60 * 60 * 8)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _tokens(user: User) -> schemas.TokenOut:
    return schemas.TokenOut(access_token=create_access_token(user.id),
                            refresh_token=create_refresh_token(user.id))


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- User auth (JWT) ----------
@app.post("/auth/signup", response_model=schemas.UserOut, status_code=201)
def signup(body: schemas.SignupIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    # is_admin is never settable from public signup.
    user = User(email=body.email, full_name=body.full_name,
                password_hash=hash_password(body.password), is_admin=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _tokens(user)


@app.post("/auth/refresh", response_model=schemas.TokenOut)
def refresh(body: schemas.RefreshIn, db: Session = Depends(get_db)):
    user_id = decode_token(body.refresh_token, "refresh")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return _tokens(user)


@app.get("/me", response_model=schemas.UserOut)
def my_profile(user: User = Depends(current_user)):
    return user


# ---------- Admin auth (server session cookie) ----------
@app.post("/admin/login")
def admin_login(body: schemas.LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not user.is_admin or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin credentials")
    request.session.clear()
    request.session["admin_id"] = user.id
    return {"ok": True}


@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/admin/users", response_model=list[schemas.UserOut])
def admin_list_users(_: User = Depends(current_admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()
