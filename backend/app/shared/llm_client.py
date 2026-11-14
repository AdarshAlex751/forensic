"""Shared Groq client with exponential backoff on 429. All slices call LLMs through here."""
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

# One model per job: each model has its own free-tier rate limit.
LEAD_MODEL = "llama-3.3-70b-versatile"
EXTRACTOR_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
CHEAP_MODEL = "llama-3.1-8b-instant"


def get_llm(model: str = EXTRACTOR_MODEL, **kwargs):
    from langchain_groq import ChatGroq  # lazy: only needed by slices that call an LLM

    return ChatGroq(model=model, **kwargs)


def with_backoff(fn: Callable[[], T], retries: int = 5, base_s: float = 2.0) -> T:
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            rate_limited = "429" in str(exc) or "rate limit" in str(exc).lower()
            if not rate_limited or attempt == retries:
                raise
            time.sleep(base_s * (2**attempt) + random.random())
    raise RuntimeError("unreachable")
