"""Provider 层瞬态错误重试与上游错误原因透传的测试。

背景：New API 网关的内存保护（system memory overloaded，HTTP 503）曾使
打磨讨论整轮失败，且当时的通用错误文案不含网关返回的具体原因，排查困难。
"""

import asyncio
from types import SimpleNamespace

import httpx2
import pytest
from openai import APIStatusError, AuthenticationError

from app.ai.errors import LLMOutputError, LLMUnavailableError
from app.ai.newapi import NewAPIProvider, _status_detail


def _provider(script: list) -> tuple[NewAPIProvider, "_FakeCompletions"]:
    provider = NewAPIProvider(base_url="http://127.0.0.1:1/v1", api_key="sk-x", model="m")
    completions = _FakeCompletions(script)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return provider, completions


class _FakeCompletions:
    def __init__(self, script: list) -> None:
        self.script = script
        self.calls = 0

    async def create(self, model, messages):
        self.calls += 1
        item = self.script[min(self.calls, len(self.script)) - 1]
        if isinstance(item, Exception):
            raise item
        if hasattr(item, "choices"):
            return item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])


def _status_error(code: int, message: str) -> APIStatusError:
    body = {"error": {"message": message}}
    request = httpx2.Request("POST", "http://127.0.0.1:1/v1/chat/completions")
    response = httpx2.Response(code, request=request, json=body)
    return APIStatusError("error", response=response, body=body)


@pytest.fixture
def no_sleep(monkeypatch):
    async def _sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)


class Test瞬态重试:
    def test_503两次后成功(self, no_sleep):
        err = _status_error(503, "system memory overloaded")
        provider, completions = _provider([err, err, "正常回复"])
        assert asyncio.run(provider.generate([{"role": "user", "content": "hi"}])) == "正常回复"
        assert completions.calls == 3

    def test_503持续则带上游原因抛出(self, no_sleep):
        err = _status_error(503, "system memory overloaded (current: 92.0%)")
        provider, completions = _provider([err])
        with pytest.raises(LLMUnavailableError) as exc_info:
            asyncio.run(provider.generate([{"role": "user", "content": "hi"}]))
        assert "HTTP 503" in str(exc_info.value)
        assert "system memory overloaded" in str(exc_info.value)
        assert completions.calls == 3

    def test_超时也重试(self, no_sleep):
        from openai import APITimeoutError

        err = APITimeoutError(request=httpx2.Request("POST", "http://127.0.0.1:1"))
        provider, completions = _provider([err, "恢复"])
        assert asyncio.run(provider.generate([{"role": "user", "content": "hi"}])) == "恢复"

    def test_401不重试(self, no_sleep):
        body = {"error": {"message": "invalid key"}}
        request = httpx2.Request("POST", "http://127.0.0.1:1/v1/chat/completions")
        response = httpx2.Response(401, request=request, json=body)
        err = AuthenticationError("unauthorized", response=response, body=body)
        provider, completions = _provider([err])
        with pytest.raises(LLMUnavailableError, match="令牌无效"):
            asyncio.run(provider.generate([{"role": "user", "content": "hi"}]))
        assert completions.calls == 1

    def test_空响应仍报输出错误(self, no_sleep):
        provider, _ = _provider([SimpleNamespace(choices=[])])
        with pytest.raises(LLMOutputError, match="返回内容为空"):
            asyncio.run(provider.generate([{"role": "user", "content": "hi"}]))


class Test错误原因提取:
    def test_嵌套error_message(self):
        exc = _status_error(503, "system memory overloaded")
        assert _status_detail(exc) == "system memory overloaded"

    def test_无body给通用提示(self):
        request = httpx2.Request("POST", "http://127.0.0.1:1")
        response = httpx2.Response(500, request=request)
        exc = APIStatusError("error", response=response, body=None)
        assert _status_detail(exc) == "请检查服务与渠道状态"

    def test_超长截断(self):
        exc = _status_error(503, "x" * 200)
        assert len(_status_detail(exc)) == 120
