"""Terminal formatting helpers for doctor output."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from procontext.cli.doctor.models import CheckResult

_LABEL_WIDTH = 22


def format_result(result: CheckResult) -> str:
    """Format a check result for terminal output."""
    dots = "." * (_LABEL_WIDTH - len(result.name))
    if result.fixed:
        status = "FIXED"
    elif result.status == "ok":
        status = "ok"
    elif result.status == "warn":
        status = "WARN"
    else:
        status = "FAIL"
    line = f"  {result.name} {dots} {status}"
    if result.detail:
        if result.status == "fail" and not result.fixed:
            line += f"\n    {result.detail}"
            if result.fix_hint:
                line += f"\n    Fix: {result.fix_hint}"
        else:
            line += f" ({result.detail})"
    return line
