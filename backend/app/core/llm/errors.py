class LLMError(Exception):
    """Raised when the LLM returns None, a refusal, or an unexpected response."""
