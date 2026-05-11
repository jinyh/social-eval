class SocialEvalError(Exception):
    pass


class IngestionError(SocialEvalError):
    pass


class KnowledgeError(SocialEvalError):
    pass


class EvaluationError(SocialEvalError):
    pass


class ProviderCallError(EvaluationError):
    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider


class ProviderTimeoutError(ProviderCallError):
    def __init__(self, provider: str, timeout: float):
        super().__init__(provider, f"Timed out after {timeout}s")
        self.timeout = timeout


class AuthError(SocialEvalError):
    pass


class NotFoundError(SocialEvalError):
    pass
