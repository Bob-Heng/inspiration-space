"""结构化调用管线单元测试：mock LLM，覆盖合法/非法 JSON/缺字段/业务校验四类用例。"""

import asyncio
import json

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import (
    BusinessValidationError,
    LLMOutputError,
    LLMProvider,
    LLMUnavailableError,
    Message,
    run_structured_call,
)
from app.models import AiCall, Base


class DemoOutput(BaseModel):
    title: str = Field(min_length=1)
    score: int


class FakeProvider(LLMProvider):
    """mock LLM：reply 为字符串时原样返回，为异常时抛出。"""

    provider_name = "fake"
    model = "fake-model"

    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply

    async def generate(self, messages: list[Message]) -> str:
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _run(db: Session, reply: str | Exception, validate_business=None) -> DemoOutput:
    return asyncio.run(
        run_structured_call(
            db,
            FakeProvider(reply),
            prompt_version="demo.v1",
            schema=DemoOutput,
            messages=[{"role": "user", "content": "测试输入"}],
            validate_business=validate_business,
        )
    )


def _only_ai_call(db: Session) -> AiCall:
    calls = list(db.scalars(select(AiCall)))
    assert len(calls) == 1
    return calls[0]


class TestStructuredPipeline:
    def test_合法输出通过并留痕(self, db_session):
        raw = json.dumps({"title": "有效输出", "score": 3}, ensure_ascii=False)
        result = _run(db_session, raw)

        assert result == DemoOutput(title="有效输出", score=3)
        call = _only_ai_call(db_session)
        assert call.provider == "fake"
        assert call.model == "fake-model"
        assert call.prompt_version == "demo.v1"
        assert "测试输入" in call.input_snapshot
        assert call.output == raw

    def test_容忍markdown围栏包裹的JSON(self, db_session):
        raw = "```json\n{\"title\": \"带围栏\", \"score\": 1}\n```"
        result = _run(db_session, raw)
        assert result.title == "带围栏"

    def test_非法JSON被拒绝并留痕(self, db_session):
        with pytest.raises(LLMOutputError, match="不是合法 JSON"):
            _run(db_session, "这不是 JSON")

        call = _only_ai_call(db_session)
        assert call.output.startswith("调用失败：")
        assert "这不是 JSON" in call.output

    def test_缺字段被拒绝并留痕(self, db_session):
        with pytest.raises(LLMOutputError, match="Schema 校验"):
            _run(db_session, '{"title": "缺少 score"}')

        call = _only_ai_call(db_session)
        assert call.output.startswith("调用失败：")
        assert "缺少 score" in call.output  # 原始输出摘录一并留存

    def test_业务校验拒绝并留痕(self, db_session):
        def reject_negative(data: DemoOutput) -> DemoOutput:
            if data.score < 0:
                raise BusinessValidationError("score 不得为负")
            return data

        with pytest.raises(BusinessValidationError, match="score 不得为负"):
            _run(db_session, '{"title": "x", "score": -1}', validate_business=reject_negative)

        call = _only_ai_call(db_session)
        assert call.output.startswith("调用失败：")
        assert "score 不得为负" in call.output

    def test_网关不可达留痕并抛出(self, db_session):
        with pytest.raises(LLMUnavailableError):
            _run(db_session, LLMUnavailableError("New API 网关不可达，请确认已运行 启动网关.bat"))

        call = _only_ai_call(db_session)
        assert call.output == "调用失败：New API 网关不可达，请确认已运行 启动网关.bat"

    def test_业务校验通过时返回校验后的数据(self, db_session):
        def normalize(data: DemoOutput) -> DemoOutput:
            return DemoOutput(title=data.title.strip(), score=data.score)

        result = _run(db_session, '{"title": "  带空格  ", "score": 2}', validate_business=normalize)
        assert result.title == "带空格"
