"""The CrashLens logo, drawn in code: a lens with a heartbeat line inside."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

BLUE_TOP = "#3b82f6"
BLUE_BOTTOM = "#1d4ed8"


def draw(p: QPainter, size: float) -> None:
    s = size
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # rounded square tile
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0, QColor(BLUE_TOP))
    grad.setColorAt(1, QColor(BLUE_BOTTOM))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.24, s * 0.24)
    # lens ring
    white = QColor("#ffffff")
    ring = QPen(white, s * 0.085)
    ring.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(ring)
    p.setBrush(Qt.BrushStyle.NoBrush)
    c = QPointF(s * 0.44, s * 0.44)
    r = s * 0.25
    p.drawEllipse(c, r, r)
    # handle
    handle = QPen(white, s * 0.11)
    handle.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(handle)
    p.drawLine(QPointF(s * 0.63, s * 0.63), QPointF(s * 0.80, s * 0.80))
    # heartbeat line inside the lens
    beat = QPen(white, s * 0.05)
    beat.setCapStyle(Qt.PenCapStyle.RoundCap)
    beat.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(beat)
    path = QPainterPath(QPointF(s * 0.26, s * 0.45))
    for x, y in ((0.35, 0.45), (0.40, 0.33), (0.47, 0.56), (0.52, 0.42), (0.62, 0.42)):
        path.lineTo(QPointF(s * x, s * y))
    p.drawPath(path)


def pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    draw(p, size)
    p.end()
    return pm


def icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(pixmap(s))
    return ic
