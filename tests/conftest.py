from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from crashlens.checks.base import CheckContext  # noqa: E402
from crashlens.core.runner import FakeRunner  # noqa: E402

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def evt(eid, provider, time, message="", data=(), level=2):
    return {
        "Id": eid,
        "Provider": provider,
        "Time": time,
        "Level": level,
        "Message": message,
        "Data": list(data),
    }


@pytest.fixture
def fake():
    return FakeRunner()


@pytest.fixture
def ctx(fake):
    return CheckContext(runner=fake, is_windows=True, now=NOW)
