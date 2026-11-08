"""Remove personal details from report data before it is shared.

IPv4 addresses are deliberately not redacted: they are rare in CrashLens data and a
pattern for them also matches four-part version numbers (e.g. 31.0.15.5222), which
would make reports misleading.
"""

from __future__ import annotations

import re
from typing import Any

from crashlens.core.models import SystemInfo

_USER_PATH = re.compile(r"(?i)\b([A-Z]:\\Users\\)(?!<user>)[^\\/\s\"']+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_SERIAL_HINT = re.compile(r"(?i)(serial(?:\s*number)?\s*[:=]\s*)\S+")

# Words too generic to replace safely if someone's account is named like this.
_GENERIC = {"user", "admin", "administrator", "owner", "pc", "home", "desktop", "laptop", "demo"}


class Redactor:
    def __init__(self, system: SystemInfo | None = None, extra_terms: tuple[str, ...] = ()) -> None:
        self._terms: list[tuple[re.Pattern[str], str]] = []
        if system:
            self._add(system.user_name, "<user>")
            self._add(system.computer_name, "<computer>")
        for t in extra_terms:
            self._add(t, "<redacted>")

    def _add(self, term: str, placeholder: str) -> None:
        term = (term or "").strip()
        if len(term) < 3 or term.lower() in _GENERIC:
            return
        pattern = re.compile(rf"(?i)(?<![\w]){re.escape(term)}(?![\w])")
        self._terms.append((pattern, placeholder))
        # Longest first, so "PAULIUS-PC" is replaced before "paulius" alone.
        self._terms.sort(key=lambda t: -len(t[0].pattern))

    def text(self, s: str) -> str:
        if not s:
            return s
        s = _USER_PATH.sub(r"\1<user>", s)
        s = _EMAIL.sub("<email>", s)
        s = _MAC.sub("<mac>", s)
        s = _SERIAL_HINT.sub(r"\1<serial>", s)
        for pattern, placeholder in self._terms:
            s = pattern.sub(placeholder, s)
        return s

    def data(self, obj: Any) -> Any:
        """Recursively redact every string in a JSON-like structure."""
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            return {k: self.data(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.data(v) for v in obj]
        return obj
