"""Runtime environment defaults shared by project entry points."""

from __future__ import annotations

import os


def configure_runtime_env() -> None:
    """Set lightweight, provider-agnostic threading defaults."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

