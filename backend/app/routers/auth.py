"""认证路由：登录 / 登出 / 当前用户。"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_initial_user, has_any_user, recover_password, require_user
from ..db import get_db
from ..models import User
from ..security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CurrentUser(BaseModel):
    username: str


@router.post("/login", response_model=CurrentUser)
def login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
) -> CurrentUser:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "bad_credentials", "zh": "用户名或密码错误", "en": "Wrong username or password"},
        )
    request.session["user_id"] = user.id
    return CurrentUser(username=user.username)


@router.get("/status")
def auth_status(db: Session = Depends(get_db)) -> dict:
    """公开接口：是否已初始化账号，以及可用的找回方式（注册时留了哪些信息）。"""
    from ..models import User
    from sqlalchemy import select as _select

    initialized = has_any_user(db)
    methods = []
    if initialized:
        user = db.scalar(_select(User).limit(1))
        if user.phone:
            methods.append("phone")
        if user.birthday:
            methods.append("birthday")
    return {"initialized": initialized, "recovery_methods": methods}


class RecoverIn(BaseModel):
    method: str  # phone | birthday
    value: str
    new_password: str


@router.post("/recover", response_model=CurrentUser)
def recover(payload: RecoverIn, request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    """找回密码：手机号/生日校验通过即重置并登录。"""
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=422, detail="密码至少 6 位")
    user = recover_password(
        db, payload.method, payload.value, payload.new_password
    )
    request.session["user_id"] = user.id
    return CurrentUser(username=user.username)


class SetupIn(BaseModel):
    username: str
    password: str
    phone: str | None = None
    birthday: str | None = None  # YYYY-MM-DD


@router.post("/setup", response_model=CurrentUser)
def setup(payload: SetupIn, request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    """首次启动初始化账号（仅 users 表为空时可用），成功后直接登录。"""
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="用户名不能为空")
    if len(payload.password) < 6:
        raise HTTPException(status_code=422, detail="密码至少 6 位")
    from datetime import date as _date

    birthday = None
    if payload.birthday:
        try:
            birthday = _date.fromisoformat(payload.birthday)
        except ValueError:
            raise HTTPException(status_code=422, detail="生日格式应为 YYYY-MM-DD")
    user = create_initial_user(
        db, username, payload.password, phone=payload.phone, birthday=birthday
    )
    request.session["user_id"] = user.id
    return CurrentUser(username=user.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=CurrentUser)
def me(user: User = Depends(require_user)) -> CurrentUser:
    return CurrentUser(username=user.username)
