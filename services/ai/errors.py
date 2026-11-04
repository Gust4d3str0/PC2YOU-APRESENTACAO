class AIError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class AIInvalidResponseError(AIError):
    """Diagnostics contain paths/types/categories only, never raw model content."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__("invalid_response", "A IA retornou uma análise inválida. Tente novamente.", 502)


class ContractViolation(ValueError):
    def __init__(self, field, category, expected, received):
        self.field, self.category = field, category
        self.expected, self.received = expected, received
        super().__init__(category)

    def issue(self):
        return {"field": self.field, "category": self.category,
                "expected": self.expected, "received": self.received}
