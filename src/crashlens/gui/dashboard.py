"""Dashboard widgets: the health-score ring and the PC info tiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QWidget

from crashlens.gui import style as theme

GB = 1024**3


class ScoreRing(QWidget):
    """A ring showing 0-100. ``score=None`` draws an empty ring with a dash."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.score: int | None = None
        self.setFixedSize(148, 148)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(148, 148)

    def set_score(self, score: int | None) -> None:
        self.score = score
        self.update()

    def color(self) -> str:
        if self.score is None:
            return theme.color("muted")
        if self.score >= 85:
            return theme.color("ok")
        if self.score >= 60:
            return theme.color("warn")
        return theme.color("bad")

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = 12
        rect = QRectF(w / 2 + 2, w / 2 + 2, self.width() - w - 4, self.height() - w - 4)
        p.setPen(
            QPen(QColor(theme.color("border")), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        p.drawArc(rect, 0, 360 * 16)
        if self.score is not None and self.score > 0:
            p.setPen(QPen(QColor(self.color()), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 90 * 16, -int(360 * 16 * self.score / 100))
        p.setPen(QColor(theme.color("text")))
        f = QFont(self.font())
        f.setPointSize(round(theme.base_pt() * 2.6))
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        text = "-" if self.score is None else str(self.score)
        p.drawText(self.rect().adjusted(0, -10, 0, -10), Qt.AlignmentFlag.AlignCenter, text)
        f.setPointSize(max(theme.base_pt() - 1, 8))
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(theme.color("muted")))
        p.drawText(self.rect().adjusted(0, 44, 0, 0), Qt.AlignmentFlag.AlignCenter, "out of 100")
        p.end()


@dataclass
class TileInfo:
    caption: str
    value: str
    detail: str = ""
    level: str = "normal"  # normal / ok / warn / bad
    bar: int | None = None  # 0-100 used


class Tile(QFrame):
    def __init__(self, info: TileInfo, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.info = info
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        cap = QLabel(info.caption.upper())
        cap.setObjectName("Badge")
        cap.setStyleSheet(f"color:{theme.color('muted')}")
        lay.addWidget(cap)
        val = QLabel(info.value)
        val.setObjectName("H3")
        if info.level in ("ok", "warn", "bad"):
            val.setStyleSheet(f"color:{theme.color(info.level)}")
        val.setWordWrap(True)
        lay.addWidget(val)
        if info.bar is not None:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(max(0, min(100, info.bar)))
            bar.setTextVisible(False)
            col = (
                theme.color(info.level) if info.level in ("warn", "bad") else theme.color("accent")
            )
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {col}; border-radius: 5px; }}")
            lay.addWidget(bar)
        if info.detail:
            d = QLabel(info.detail)
            d.setObjectName("Small")
            d.setWordWrap(True)
            lay.addWidget(d)
        lay.addStretch(1)


def _gb(n: float) -> str:
    v = n / GB
    return f"{v:.0f} GB" if v >= 100 else f"{v:.1f} GB"


def _duration(hours: float) -> str:
    if hours < 1:
        return "less than an hour"
    if hours < 48:
        h = round(hours)
        return f"{h} hour{'s' if h != 1 else ''}"
    return f"{round(hours / 24)} days"


def tiles_from_metrics(m: dict[str, Any]) -> list[TileInfo]:
    tiles: list[TileInfo] = []
    os_ = m.get("os") or {}
    if os_:
        build = f"Build {os_['build']}" if os_.get("build") else ""
        tiles.append(TileInfo("Windows", os_.get("caption") or "Windows", build))
        if os_.get("ram_used_pct") is not None:
            pct = int(os_["ram_used_pct"])
            total = os_.get("ram_total_gb")
            tiles.append(
                TileInfo(
                    "Memory",
                    f"{pct}% in use",
                    f"of {total:g} GB" if total else "",
                    "bad" if pct >= 90 else "warn" if pct >= 80 else "normal",
                    pct,
                )
            )
        if os_.get("uptime_hours") is not None:
            hours = float(os_["uptime_hours"])
            pending = os_.get("reboot_pending")
            tiles.append(
                TileInfo(
                    "Running for",
                    _duration(hours),
                    "Restart needed to finish updates" if pending else "since last restart",
                    "warn" if pending or hours > 14 * 24 else "normal",
                )
            )
    for d in m.get("drives") or []:
        size, free = float(d.get("size") or 0), float(d.get("free") or 0)
        if size <= 0:
            continue
        free_pct = free / size * 100
        level = (
            "bad"
            if free_pct < 5 or free < 5 * GB
            else ("warn" if free_pct < 10 or free < 15 * GB else "normal")
        )
        name = f"Drive {d.get('drive', '?')}"
        if d.get("label"):
            name += f" ({d['label']})"
        tiles.append(
            TileInfo(name, f"{_gb(free)} free", f"of {_gb(size)}", level, round(100 - free_pct))
        )
    rel = m.get("reliability")
    if rel is not None:
        tiles.append(
            TileInfo(
                "Stability (Windows' rating)",
                f"{rel:g} out of 10",
                "Based on recent crashes and failures",
                "bad" if rel < 3 else "warn" if rel < 6 else "ok",
                round(rel * 10),
            )
        )
    upd = m.get("updates")
    if upd:
        days = int(upd.get("days", 0))
        when = "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
        tiles.append(
            TileInfo(
                "Last Windows update",
                when,
                str(upd.get("name") or ""),
                "bad" if days >= 90 else "warn" if days >= 45 else "ok",
            )
        )
    prot = m.get("protection")
    if prot:
        on = [p for p in prot if p.get("enabled")]
        if on:
            current = all(p.get("up_to_date") for p in on)
            tiles.append(
                TileInfo(
                    "Virus protection",
                    "On" if current else "On, needs update",
                    on[0].get("name", ""),
                    "ok" if current else "warn",
                )
            )
        else:
            tiles.append(TileInfo("Virus protection", "Off", prot[0].get("name", ""), "bad"))
    if m.get("startup_count") is not None:
        n = int(m["startup_count"])
        tiles.append(
            TileInfo(
                "Start with Windows",
                f"{n} program{'s' if n != 1 else ''}",
                "",
                "warn" if n >= 12 else "normal",
            )
        )
    return tiles
