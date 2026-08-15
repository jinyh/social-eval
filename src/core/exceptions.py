class SocialEvalError(Exception):
    pass


class IngestionError(SocialEvalError):
    pass


class KnowledgeError(SocialEvalError):
    pass


class EvaluationError(SocialEvalError):
    pass


class ProviderCallError(EvaluationError):
    def __init__(
        self,
        provider: str,
        message: str,
        *,
        raw_response: str | None = None,
        finish_reason: str | None = None,
    ):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.raw_response = raw_response
        self.finish_reason = finish_reason


class ProviderResponseValidationError(ProviderCallError):
    """供应商已返回内容，但内容不符合结构化输出契约。"""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        raw_response: str,
        invalid_fields: tuple[str, ...] = (),
    ):
        super().__init__(provider, message, raw_response=raw_response)
        self.invalid_fields = invalid_fields


class ProviderTimeoutError(ProviderCallError):
    def __init__(self, provider: str, timeout: float):
        super().__init__(provider, f"Timed out after {timeout}s")
        self.timeout = timeout


class AuthError(SocialEvalError):
    pass


class NotFoundError(SocialEvalError):
    pass
