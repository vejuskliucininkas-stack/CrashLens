"""User settings, saved as a small JSON file. Bad or missing files fall back to defaults."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

THEMES = ("system", "light", "dark")
TEXT_SIZES = ("normal", "large", "xlarge")
LOOKBACK_CHOICES = (7, 30, 90, 365)


@dataclass
class Settings:
    theme: str = "system"  # "system" follows Windows' light/dark setting
    text_size: str = "normal"
    lookback_days: int = 30
    show_details: bool = False  # technical pages and details, for experts
    welcomed: bool = False  # the welcome screen was shown once

    def validated(self) -> Settings:
        return Settings(
            welcomed=bool(self.welcomed),
            theme=self.theme if self.theme in THEMES else "system",
            text_size=self.text_size if self.text_size in TEXT_SIZES else "normal",
            lookback_days=(self.lookback_days if self.lookback_days in LOOKBACK_CHOICES else 30),
            show_details=bool(self.show_details),
        )

    @classmethod
    def load(cls, path: Path | None) -> Settings:
        if path is None or not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        try:
            return cls(**{k: v for k, v in raw.items() if k in known}).validated()
        except TypeError:
            return cls()

    def save(self, path: Path | None) -> bool:
        if path is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(asdict(self.validated()), indent=2), encoding="utf-8")
            tmp.replace(path)
            return True
        except OSError:
            return False
