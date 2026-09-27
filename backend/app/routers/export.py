"""观点库 Docx 导出接口（TASK-019）：原始观点 / 分类观点，格式沿用原系统（docs/02 §6）。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_user
from ..db import get_db
from ..domain.docx_export import build_classified_docx, build_viewpoints_docx
from ..domain.viewpoints import classified_viewpoints
from ..models import Viewpoint

router = APIRouter(
    prefix="/api/export",
    tags=["export"],
    dependencies=[Depends(require_user)],
)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _docx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.get("/viewpoints")
def export_viewpoints(db: Session = Depends(get_db)) -> Response:
    """导出原始观点.docx：全部观点（含悬置/否定，保留标记），按库内编号排序。"""
    viewpoints = list(db.scalars(select(Viewpoint).order_by(Viewpoint.id)))
    return _docx_response(build_viewpoints_docx(viewpoints), "原始观点.docx")


@router.get("/classified")
def export_classified(db: Session = Depends(get_db)) -> Response:
    """导出分类观点.docx：道/法/术三节，已否定不列入，悬置保留标记，组内按来源日期排序。"""
    return _docx_response(build_classified_docx(classified_viewpoints(db)), "分类观点.docx")
