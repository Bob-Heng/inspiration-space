"""AI 调用异常体系。异常信息面向用户，不得包含密钥等敏感信息。"""


class LLMError(Exception):
    """AI 调用异常基类。"""


class LLMConfigError(LLMError):
    """AI 服务配置缺失（如环境变量未设置）。"""


class LLMUnavailableError(LLMError):
    """AI 服务不可达：网关未启动、超时或返回非 200。"""


class LLMOutputError(LLMError):
    """AI 输出不可用：不是合法 JSON、未通过 Schema 校验或业务校验。"""

    def __init__(self, message: str, raw_output: str | None = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output


class BusinessValidationError(LLMOutputError):
    """业务校验失败（Schema 合法但违反业务规则）。"""
