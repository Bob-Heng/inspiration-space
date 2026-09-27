"""AI 服务配置解析的单元测试：界面配置优先、环境变量兜底、密钥回显脱敏。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.errors import LLMConfigError
from app.ai.provider_config import (
    PRESETS,
    mask_api_key,
    resolve_llm_config,
    resolve_llm_provider,
)
from app.db import Base
from app.models import LlmSetting


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestResolveLlmConfig:
    def test_界面配置优先于环境变量(self, db):
        db.add(LlmSetting(id=1, provider_key="deepseek", api_key="sk-test-key"))
        db.commit()
        resolved = resolve_llm_config(db)
        assert resolved.source == "ui"
        assert resolved.provider_key == "deepseek"
        assert resolved.base_url == PRESETS["deepseek"]["base_url"]
        assert resolved.label == "DeepSeek"

    def test_界面未配置时回退环境变量(self, db):
        resolved = resolve_llm_config(db)
        # 测试环境 .env 已配置 New API，则回退生效；未配置则为 None
        if resolved is not None:
            assert resolved.source == "env"
            assert resolved.provider_key == "env"

    def test_界面有行但无密钥视为未配置(self, db):
        db.add(LlmSetting(id=1, provider_key="openai"))
        db.commit()
        resolved = resolve_llm_config(db)
        assert resolved is None or resolved.source == "env"

    def test_自定义服务商缺少base_url报错(self, db):
        db.add(LlmSetting(id=1, provider_key="custom", api_key="sk-x"))
        db.commit()
        with pytest.raises(LLMConfigError, match="Base URL"):
            resolve_llm_config(db)

    def test_自定义服务商自填base_url(self, db):
        db.add(
            LlmSetting(
                id=1, provider_key="custom", api_key="sk-x",
                base_url="https://example.com/v1", model="m1",
            )
        )
        db.commit()
        resolved = resolve_llm_config(db)
        assert resolved.base_url == "https://example.com/v1"
        assert resolved.model == "m1"

    def test_构造Provider携带预设标签(self, db):
        db.add(LlmSetting(id=1, provider_key="moonshot", api_key="sk-x", model="kimi-k2"))
        db.commit()
        provider = resolve_llm_provider(db)
        assert provider.provider_name == "moonshot"
        assert provider.label == "Kimi（月之暗面）"
        assert provider.model == "kimi-k2"
        assert provider.base_url == PRESETS["moonshot"]["base_url"]


class TestMaskApiKey:
    def test_只回显末四位(self):
        assert mask_api_key("sk-abcdefgh1234") == "****1234"

    def test_空值返回空(self):
        assert mask_api_key(None) is None
        assert mask_api_key("") is None


class TestSaveBehavior:
    def test_切换服务商清除旧密钥(self, db):
        from app.routers.settings import LlmSettingsIn, save_llm_settings

        save_llm_settings(LlmSettingsIn(provider_key="deepseek", api_key="sk-old"), db)
        result = save_llm_settings(LlmSettingsIn(provider_key="openai"), db)
        assert result["saved"]["has_api_key"] is False

    def test_同服务商保存留空则保留密钥(self, db):
        from app.routers.settings import LlmSettingsIn, save_llm_settings

        save_llm_settings(LlmSettingsIn(provider_key="deepseek", api_key="sk-old"), db)
        result = save_llm_settings(LlmSettingsIn(provider_key="deepseek"), db)
        assert result["saved"]["has_api_key"] is True
        assert result["saved"]["api_key_masked"] == "****-old"

    def test_未知服务商被拒绝(self, db):
        from fastapi import HTTPException

        from app.routers.settings import LlmSettingsIn, save_llm_settings

        with pytest.raises(HTTPException):
            save_llm_settings(LlmSettingsIn(provider_key="unknown"), db)

class TestModelSelection:
    def test_保存下拉选择的模型(self, db):
        from app.routers.settings import LlmSettingsIn, save_llm_settings

        result = save_llm_settings(
            LlmSettingsIn(
                provider_key="deepseek", api_key="sk-x", model="deepseek-chat"
            ),
            db,
        )
        assert result["saved"]["model"] == "deepseek-chat"
        assert result["effective"]["model"] == "deepseek-chat"

    def test_未选模型时保存为空(self, db):
        from app.routers.settings import LlmSettingsIn, save_llm_settings

        result = save_llm_settings(
            LlmSettingsIn(provider_key="deepseek", api_key="sk-x"), db
        )
        assert result["saved"]["model"] is None

class TestInitialSetup:
    def test_空库可初始化且仅一次(self, db):
        from fastapi import HTTPException

        from app.auth import create_initial_user, has_any_user

        assert not has_any_user(db)
        user = create_initial_user(db, "bob", "secret1")
        assert user.username == "bob"
        assert has_any_user(db)
        with pytest.raises(HTTPException):
            create_initial_user(db, "eve", "hacked")
