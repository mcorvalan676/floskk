from pyodide.ffi import run_sync, to_js

from services.ai.base import AIProviderError, AIUnavailableError


class CloudflareWorkersAIProvider:
    def __init__(self, worker_env, model):
        binding = getattr(worker_env, "AI", None) if worker_env is not None else None
        if binding is None:
            raise AIUnavailableError("Workers AI binding is not configured.")
        self.binding = binding
        self.model = model

    def generate(self, messages, max_tokens=350):
        try:
            result = run_sync(
                self.binding.run(
                    self.model,
                    to_js(
                        {
                            "messages": messages,
                            "max_tokens": max_tokens,
                            "temperature": 0.3,
                        }
                    ),
                )
            )
            if hasattr(result, "to_py"):
                result = result.to_py()
            answer = result.get("response") if isinstance(result, dict) else None
            if not isinstance(answer, str) or not answer.strip():
                raise AIProviderError("Workers AI returned an empty response.")
            return answer.strip()
        except AIProviderError:
            raise
        except Exception as error:
            raise AIProviderError("Workers AI request failed.") from error
