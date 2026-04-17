"""Typed error record for pipeline nodes.

Replaces the bare ``except Exception`` -> ``errors.append(str)`` idiom with a
structured record that can be surfaced by the analysis progress endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class NodeError:
    node: str
    message: str
    exc_type: str = ""
    section_index: int | None = None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "message": self.message,
            "exc_type": self.exc_type,
            "section_index": self.section_index,
            "at": self.at.isoformat(),
        }

    def as_log_string(self) -> str:
        prefix = f"[{self.node}]"
        if self.section_index is not None:
            prefix += f"[sec={self.section_index}]"
        return f"{prefix} {self.exc_type}: {self.message}" if self.exc_type else f"{prefix} {self.message}"


def append_node_error(
    errors: list,
    *,
    node: str,
    exc: BaseException,
    section_index: int | None = None,
) -> None:
    """Append a structured node error to a pipeline state's ``errors`` list.

    The legacy callers expected ``list[str]``; we keep that contract by
    writing the dataclass's log string, but callers that want structured
    data can use :class:`NodeError` directly.
    """
    err = NodeError(
        node=node,
        message=str(exc) or exc.__class__.__name__,
        exc_type=exc.__class__.__name__,
        section_index=section_index,
    )
    errors.append(err.as_log_string())
