from __future__ import annotations

import re
from typing import Optional


def clamp_max_tokens(requested: Optional[int], *, hard_cap: int = 2048) -> Optional[int]:
    """Return a safe max_tokens for OpenAI-compatible servers.

    - None/<=0: omit max_tokens (server decides)
    - Otherwise: cap to hard_cap to avoid huge generations by default
    """
    if requested is None:
        return None
    try:
        requested_int = int(requested)
    except Exception:
        return None
    if requested_int <= 0:
        return None
    return min(requested_int, int(hard_cap))


def max_tokens_from_context_error(message: str, *, safety_margin: int = 32) -> Optional[int]:
    """Parse 'maximum context length' errors and return allowed max_tokens.

    Works with messages like:
      "This model's maximum context length is 8192 tokens and your request has 336 input tokens (...)."
    """
    if not message:
        return None

    m = re.search(
        r"maximum context length is\s+(?P<context>\d+)\s+tokens.*request has\s+(?P<input>\d+)\s+input tokens",
        message,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None

    try:
        context_len = int(m.group("context"))
        input_tokens = int(m.group("input"))
    except Exception:
        return None

    allowed = context_len - input_tokens - int(safety_margin)
    if allowed <= 0:
        return 1
    return allowed

