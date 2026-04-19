"""Rollout flags for the v2 prompt library."""

from __future__ import annotations

import os


def legacy_prompts_enabled() -> bool:
    """When true, call sites keep using their old inline strings.

    Flip to 1 as an emergency rollback without a code change. Defaults
    to off so the new v2 prompts are the source of truth.
    """
    return os.getenv("LEGACY_PROMPTS", "").strip() in ("1", "true", "TRUE")


__all__ = ["legacy_prompts_enabled"]
