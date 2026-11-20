"""Optional terminal colors (stdlib only, plain ANSI codes).

Colors are used only when stdout is an interactive terminal, so piped output, files and
tests stay plain text. Set NO_COLOR=1 (https://no-color.org) to turn them off.
"""

from __future__ import annotations

import os
import sys

_CODES = {
    "bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36",
}

# One color per common action type, so the same action always looks the same.
ACTION_COLORS = {
    "DEPOSIT": "green",
    "REPAYMENT": "green",
    "WITHDRAWAL": "yellow",
    "DISBURSEMENT": "magenta",
    "TRANSFER": "blue",
    "FEE_CHARGE": "red",
}


def use_color(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def paint(text: str, *styles: str, enabled: bool = True) -> str:
    """Wrap `text` in ANSI codes. Returns it unchanged when disabled or with no styles."""
    codes = [_CODES[s] for s in styles if s in _CODES]
    if not enabled or not codes or not text:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"
