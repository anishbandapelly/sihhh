class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        self.code, self.message, self.status, self.retryable = code, message, status, retryable
        super().__init__(message)

def require(condition, message, code='INVALID_STATE_TRANSITION', status=400):
    if not condition:
        raise DomainError(code, message, status)

