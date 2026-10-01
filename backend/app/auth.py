"""登录认证：单用户密码 + 签名 Cookie Session。"""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User
from .security import hash_password

logger = logging.getLogger(__name__)

ADMIN_USERNAME = "admin"


def ensure_admin_user(db: Session) -> None:
    """兼容路径：users 表为空且设置了 INSPIRATION_ADMIN_PASSWORD 时创建 admin。
    未设置环境变量则不创建——由用户在首次启动的初始化界面自行设置账号。"""
    exists = db.scalar(select(User.id).limit(1))
    if exists is not None:
        return
    if not config.ADMIN_PASSWORD:
        logger.info("users 表为空且未配置环境变量密码，等待首次启动初始化账号")
        return
    db.add(
        User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(config.ADMIN_PASSWORD),
        )
    )
    db.commit()
    logger.info("已创建管理员账户 %s", ADMIN_USERNAME)


def has_any_user(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


def create_initial_user(
    db: Session,
    username: str,
    password: str,
    phone: str | None = None,
    birthday=None,
) -> User:
    """首次启动初始化：仅当 users 表为空时允许创建，创建后表即关闭初始化通道。
    phone/birthday 可选，仅本地保存，用于找回密码。"""
    if has_any_user(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "already_initialized", "zh": "账号已初始化，不能重复创建", "en": "Account already initialized"},
        )
    user = User(
        username=username,
        password_hash=hash_password(password),
        phone=phone or None,
        birthday=birthday,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def recover_password(db: Session, method: str, value: str, new_password: str) -> User:
    """通过注册时留下的手机号/生日找回：校验通过即重置密码（一次机会）。"""
    user = db.scalar(select(User).limit(1))
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if method == "phone":
        stored = user.phone
    elif method == "birthday":
        stored = str(user.birthday) if user.birthday else None
    else:
        raise HTTPException(status_code=422, detail="非法找回方式")
    if not stored:
        raise HTTPException(status_code=403, detail={"code": "recovery_not_available", "zh": "注册时未提供该信息，无法以此找回", "en": "This recovery method was not set up"})
    if stored != value.strip():
        raise HTTPException(status_code=401, detail={"code": "recovery_mismatch", "zh": "信息不正确", "en": "Incorrect information"})
    user.password_hash = hash_password(new_password)
    db.commit()
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """受保护接口依赖：未登录返回 401。"""
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录"
        )
    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效"
        )
    return user
