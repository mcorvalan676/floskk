from typing import Protocol


class AIProviderError(Exception):
    pass


class AIUnavailableError(AIProviderError):
    pass


class AIProvider(Protocol):
    def generate(self, messages, max_tokens=350):
        ...
