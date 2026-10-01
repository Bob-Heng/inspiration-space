"""业务错误：双语 detail，前端按界面语言取对应文案。"""

from fastapi import HTTPException


def biz_error(status_code: int, code: str, zh: str, en: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "zh": zh, "en": en or zh},
    )
