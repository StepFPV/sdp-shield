#!/usr/bin/env python3
"""SDP Shield: unofficial graphical front-end for the Cato Networks Linux client.

It runs the `cato-sdp` command line tool (status, start, stop, version) and
shows the result. It never reads credentials and talks to no server of its own.
"""

import datetime as dt
import faulthandler
import json
import math
import os
import re
import socket
import subprocess
import sys
import tarfile
import traceback
from dataclasses import dataclass, field

from PySide6.QtCore import (QByteArray, QPointF, QRectF, QSize, Qt, QThread,
                            QTimer, Signal)
from PySide6.QtGui import (QAction, QColor, QConicalGradient, QFont, QIcon,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox,
                               QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

__version__ = "2.0.0"

APP_NAME = "SDP Shield"
APP_ID = "sdp-shield"
CMD = "cato-sdp"
NOT_FOUND_MSG = f"'{CMD}' was not found. Is the Cato client installed?"


def _xdg(var, default):
    return os.path.join(os.environ.get(var) or os.path.expanduser(default), APP_ID)


HOME_DIR = os.path.expanduser("~")
STATE_DIR = _xdg("XDG_STATE_HOME", "~/.local/state")
CONF_DIR = _xdg("XDG_CONFIG_HOME", "~/.config")
CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache")
CLIENT_DIR = os.path.join(HOME_DIR, ".cato")          # default working dir of cato-sdp
AUTOSTART = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                         "autostart", f"{APP_ID}.desktop")

# dark palette
SIDEBAR = "#171717"
PAGE = "#1e1e1e"
CARD = "#121212"
LINE = "#343434"
GREEN = "#1b7a50"
GREEN_HI = "#2a9d6a"
GREEN_DK = "#0f5a3a"
TEXT = "#f2f2f2"
MUTED = "#8c8c8c"
FAINT = "#5a5a5a"


# --------------------------------------------------------------------------- helpers

def run(*args, timeout=15, stdin=None):
    """Run cato-sdp and return (ok, output without ANSI colour codes)."""
    try:
        p = subprocess.run([CMD, *args], capture_output=True, text=True,
                           timeout=timeout, input=stdin)
        out = (p.stdout or "") + (p.stderr or "")
        out = re.sub(r"\x1b\[[0-9;]*m", "", out).strip()
        return p.returncode == 0, out
    except FileNotFoundError:
        return False, NOT_FOUND_MSG
    except subprocess.TimeoutExpired:
        return False, "The command timed out."
    except Exception as exc:                                  # pragma: no cover
        return False, f"Error: {exc}"


def load_json(name, default):
    try:
        with open(os.path.join(CONF_DIR, name)) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(name, data):
    os.makedirs(CONF_DIR, exist_ok=True)
    tmp = os.path.join(CONF_DIR, name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, os.path.join(CONF_DIR, name))


def human_bytes(n):
    if n is None:
        return "N/A"
    for unit in ("Bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "Bytes" else f"{n:.1f} {unit}"
        n /= 1024


def font(size, weight=QFont.Normal):
    f = QFont(QApplication.font())
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


# --------------------------------------------------------------------------- SVG icons

def _gear_path():
    pts = []
    for i in range(16):
        a = math.radians(i * 22.5 - 11.25)
        r = 9.5 if i % 2 == 0 else 7.3
        pts.append(f"{12 + r * math.cos(a):.2f},{12 + r * math.sin(a):.2f}")
    return "M" + " L".join(pts) + " Z"


ICONS = {
    "home": '<path d="M12 3l7 2.8v5.4c0 4.6-3 8.3-7 9.8-4-1.5-7-5.2-7-9.8V5.8z"/>'
            '<path d="M8.8 12.2l2.3 2.3 4.3-4.6"/>',
    "stats": '<path d="M4 4v16h16"/><path d="M7.5 15.5l3.5-4 3 2.6 5-6"/>'
             '<path d="M16.2 8h2.8v2.8"/>',
    "users": '<circle cx="12" cy="8" r="3.8"/><path d="M4.5 20.5c0-3.7 3.4-6 7.5-6s7.5 2.3 7.5 6z"/>',
    "settings": f'<path d="{_gear_path()}"/><circle cx="12" cy="12" r="3"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M10.5 16.5h3"/>'
             '<circle cx="12" cy="7.8" r="0.6" fill="{c}"/>',
    "support": '<circle cx="12" cy="12" r="9.5" fill="{c}" stroke="none"/>'
               '<path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.5" stroke="{bg}" stroke-width="2"/>'
               '<circle cx="12" cy="16.6" r="1.1" fill="{bg}" stroke="none"/>',
    "feedback": '<path d="M4 4.5h16v11.5H10l-4.5 3.5V16H4z"/><path d="M8 8.5h8"/><path d="M8 12h5"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="3.5"/><path d="M9.5 4v16"/>'
               '<path d="M5.5 8h2"/><path d="M5.5 11h2"/><path d="M5.5 14h2"/>',
    "private": '<circle cx="9" cy="8" r="3.4"/><path d="M3 19.5c0-3.4 2.7-5.6 6-5.6 1.2 0 2.3.3 3.2.8"/>'
               '<circle cx="16.5" cy="14.5" r="2.4"/><path d="M16.5 17v5"/><path d="M16.5 20h1.8"/>',
    "internet": '<circle cx="10" cy="11" r="7.5"/><path d="M2.5 11h15"/>'
                '<path d="M10 3.5c2.2 2.2 2.2 12.8 0 15M10 3.5c-2.2 2.2-2.2 12.8 0 15"/>'
                '<circle cx="17.5" cy="15" r="2.4" fill="{bg}"/><path d="M17.5 17.5v5"/><path d="M17.5 20.5h1.8"/>',
    "check": '<path d="M5.5 12.5l4.2 4.2 8.8-9.4" stroke-width="3"/>',
    "close": '<path d="M5 5l14 14M19 5L5 19" stroke-width="1.6"/>',
}


def svg_pixmap(name, color, size, bg=SIDEBAR, dpr=2.0):
    body = ICONS[name].replace("{c}", color).replace("{bg}", bg)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
           f'stroke-linejoin="round">{body}</svg>')
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def write_check_svg():
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "check.svg")
    with open(path, "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                'stroke="#ffffff" stroke-width="3.2" stroke-linecap="round" '
                'stroke-linejoin="round"><path d="M5.5 12.5l4.2 4.2 8.8-9.4"/></svg>')
    return path


# --------------------------------------------------------------------------- client status

@dataclass
class Status:
    connected: bool = False
    connecting: bool = False
    daemon_ok: bool = True
    kv: dict = field(default_factory=dict)
    user: str = ""
    account: str = ""
    client_version: str = ""
    local_ip: str = ""
    raw: str = ""
    when: dt.datetime = field(default_factory=dt.datetime.now)

    @property
    def text(self):
        if self.connecting:
            return "Connecting"
        if not self.daemon_ok:
            return "Daemon not running"
        return "Connected" if self.connected else "Disconnected"

    def get(self, key):
        return self.kv.get(key, "").strip('"')

    @property
    def pop(self):
        return self.get("pop name")

    @property
    def duration(self):
        return self.get("duration")

    def bytes(self, key):
        m = re.match(r"(\d+)", self.get(key))
        return int(m.group(1)) if m else None

    @property
    def rtt(self):
        """(avg, last) in ms from the field rtt = n/min/avg/max/last."""
        m = re.match(r"(\d+)/(\d+)/(\d+)/(\d+)/(\d+)", self.get("rtt"))
        return (int(m.group(3)), int(m.group(5))) if m else None

    @property
    def session_start(self):
        m = re.match(r"(\d+):(\d\d):(\d\d)", self.duration)
        if not m:
            return None
        h, mi, s = map(int, m.groups())
        return self.when - dt.timedelta(hours=h, minutes=mi, seconds=s)


def parse_status(ok, raw):
    """Parse `cato-sdp status` output (client 5.8.x), tolerant of small variations."""
    s = Status(raw=raw)
    low = raw.lower()

    m = re.search(r"^Cato Client:\s*(\S+)", raw, re.M)
    if m:
        s.client_version = m.group(1)
    for k, v in re.findall(r"^\s*([a-z_][a-z0-9_ ]*?)\s*=\s*(.+?)\s*$", raw, re.M):
        s.kv[k.strip().lower()] = v.strip()
    m = re.search(r"^\s*Account:\s*(.+?)\s*$", raw, re.M)
    s.account = m.group(1) if m else ""
    m = re.search(r"^\s*User:\s*(.+?)\s*$", raw, re.M)
    s.user = m.group(1) if m else ""

    if "failed to deserialize cmd" in low:              # daemon busy with the handshake
        s.connecting = True
    elif re.search(r"connected_unauth|authentication is now in progress|state_connecting", low):
        s.connecting = True
    elif "failed to connect to cato client daemon" in low or "cannot open pipe" in low \
            or "was not found" in low or "not installed" in low:
        s.daemon_ok = False
    elif "state_authenticated" in low or "cato client is connected" in low:
        s.connected = True
    elif "cato client is disconnected" in low:
        s.connected = False
    else:
        s.connected = bool(re.search(r"\bconnected\b", low)) and not re.search(
            r"\b(disconnected|not connected)\b", low)
    return s


def local_ip_towards(addr):
    """Local IP used to reach the PoP (no packet is sent: UDP connect only picks a route)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
            so.connect((addr or "1.1.1.1", 443))
            return so.getsockname()[0]
    except Exception:
        return ""


class Poller(QThread):
    got = Signal(object)

    def run(self):
        ok, raw = run("status")
        st = parse_status(ok, raw)
        if st.connected:
            st.local_ip = local_ip_towards(st.get("pop address"))
        self.got.emit(st)


class Action(QThread):
    done = Signal(bool, str)

    def __init__(self, args):
        super().__init__()
        self.args = args

    def run(self):
        ok, out = run(*self.args, timeout=90)
        self.done.emit(ok, out)


class Job(QThread):
    """Run a Python function outside the GUI thread."""
    done = Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(True, self.fn() or "")
        except Exception as exc:
            self.done.emit(False, str(exc))


# --------------------------------------------------------------------------- widgets

class Wordmark(QWidget):
    """Text logo: SDP / SHIELD."""

    def __init__(self, color, size):
        super().__init__()
        self.color, self.size_ = QColor(color), size
        self.setFixedHeight(int(size * 1.55))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(self.color)
        f = font(self.size_, QFont.Light if self.size_ < 50 else QFont.Normal)
        f.setLetterSpacing(QFont.AbsoluteSpacing, -self.size_ * 0.02)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance("SDP")
        x = (self.width() - w) / 2
        p.drawText(QPointF(x, fm.ascent() * 0.98), "SDP")
        f2 = font(max(7, int(self.size_ * 0.2)), QFont.Bold)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, self.size_ * 0.27)
        p.setFont(f2)
        w2 = p.fontMetrics().horizontalAdvance("SHIELD") - self.size_ * 0.27
        p.drawText(QPointF((self.width() - w2) / 2, fm.ascent() * 0.98 + self.size_ * 0.42),
                   "SHIELD")
        p.end()


def shield_path(x0, y0, W, H):
    cx = x0 + W / 2
    sh = QPainterPath()
    sh.moveTo(cx, y0)
    sh.lineTo(x0 + W, y0 + 0.12 * H)
    sh.lineTo(x0 + W, y0 + 0.52 * H)
    sh.cubicTo(x0 + W, y0 + 0.80 * H, cx + 0.22 * W, y0 + 0.93 * H, cx, y0 + H)
    sh.cubicTo(cx - 0.22 * W, y0 + 0.93 * H, x0, y0 + 0.80 * H, x0, y0 + 0.52 * H)
    sh.lineTo(x0, y0 + 0.12 * H)
    sh.closeSubpath()
    return sh


class Shield(QWidget):
    """Shield with a round power button."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(190, 228)
        self.state = "off"       # off | on | busy
        self.angle = 0
        self.setCursor(Qt.PointingHandCursor)
        self.spin = QTimer(self)
        self.spin.timeout.connect(self._step)

    def _step(self):
        self.angle = (self.angle - 6) % 360
        self.update()

    def set_state(self, state):
        if state == self.state:
            return
        self.state = state
        if state == "busy":
            self.spin.start(16)
        else:
            self.spin.stop()
        self.update()

    def _geo(self):
        W, H = self.width() - 10, self.height() - 10
        x0, y0 = 5, 5
        cx, cy = x0 + W / 2, y0 + H * 0.46
        return x0, y0, W, H, cx, cy

    def mousePressEvent(self, ev):
        *_, W, H, cx, cy = self._geo()
        r = W * 0.38
        if (ev.position().x() - cx) ** 2 + (ev.position().y() - cy) ** 2 <= r * r:
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x0, y0, W, H, cx, cy = self._geo()

        sh = shield_path(x0, y0, W, H)

        on = self.state == "on"
        left, right = (("#1f8257", "#176845") if on else ("#3d4447", "#2d3437"))
        p.setPen(Qt.NoPen)
        p.save()
        p.setClipRect(QRectF(0, 0, cx, self.height()))
        p.setBrush(QColor(left))
        p.drawPath(sh)
        p.setClipRect(QRectF(cx, 0, self.width(), self.height()))
        p.setBrush(QColor(right))
        p.drawPath(sh)
        p.restore()

        # ring
        rr, pw = W * 0.335, W * 0.075
        ring = QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr)
        p.setBrush(Qt.NoBrush)
        if on:
            g = QConicalGradient(QPointF(cx, cy), 90)
            g.setColorAt(0.0, QColor("#1f8a5c"))
            g.setColorAt(0.5, QColor("#0e4f34"))
            g.setColorAt(1.0, QColor("#1f8a5c"))
            p.setPen(QPen(g, pw))
            p.drawEllipse(ring)
        else:
            p.setPen(QPen(QColor("#22282b"), pw))
            p.drawEllipse(ring)
            if self.state == "busy":
                g = QConicalGradient(QPointF(cx, cy), self.angle)
                g.setColorAt(0.0, QColor(GREEN_HI))
                g.setColorAt(0.75, QColor(GREEN_DK))
                g.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.setPen(QPen(g, pw, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(ring, int(self.angle * 16), int(270 * 16))

        # white disc
        rb = W * 0.29
        btn = QRadialGradient(QPointF(cx, cy - rb * 0.35), rb * 1.5)
        btn.setColorAt(0, QColor("#ffffff"))
        btn.setColorAt(1, QColor("#d6d6d6"))
        p.setPen(Qt.NoPen)
        p.setBrush(btn)
        p.drawEllipse(QPointF(cx, cy), rb, rb)
        p.setBrush(QColor(0, 0, 0, 14))
        p.drawEllipse(QPointF(cx, cy + 1), rb * 0.36, rb * 0.36)

        # power symbol
        gr = rb * 0.3
        pen = QPen(QColor(GREEN), max(3.0, rb * 0.095), Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - gr, cy - gr, 2 * gr, 2 * gr), 125 * 16, 290 * 16)
        p.drawLine(QPointF(cx, cy - gr * 1.3), QPointF(cx, cy - gr * 0.1))
        p.end()


class Toggle(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(GREEN if self.isChecked() else "#3a3a3a"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.right() - d - 3 if self.isChecked() else r.left() + 3
        p.setBrush(QColor("#ffffff" if self.isChecked() else "#8a8a8a"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()


class Radio(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(24, 24)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        p.setPen(QPen(QColor("#6a6a6a"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(2, 2, 20, 20))
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(GREEN_HI if self.isEnabled() else "#9a9a9a"))
            p.drawEllipse(QRectF(8, 8, 8, 8))
        p.end()


def pill_button(text, outline=True):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(40)
    if outline:
        b.setStyleSheet(f"""
            QPushButton {{ border: 1.5px solid {GREEN}; border-radius: 20px; color: {GREEN_HI};
                          background: transparent; font-weight: 700; font-size: 14px; padding: 0 26px; }}
            QPushButton:hover {{ background: rgba(27,122,80,0.15); }}
            QPushButton:disabled {{ color: {FAINT}; border-color: {LINE}; }}""")
    return b


def page_title(text):
    t = QLabel(text)
    t.setFont(font(34, QFont.Light))
    t.setStyleSheet("color:#dcdcdc;")
    return t


def hline():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{LINE};")
    return f


def card():
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet(f"QFrame#card {{ background:{CARD}; border-radius:9px; }}")
    return f


# --------------------------------------------------------------------------- pages

class HomePage(QWidget):
    def __init__(self, shield):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 34, 22, 22)
        lay.setSpacing(0)

        lay.addWidget(Wordmark(GREEN, 46))
        lay.addSpacing(26)
        self.status = QLabel("—")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(font(25, QFont.Bold))
        lay.addWidget(self.status)
        self.timer = QLabel("")
        self.timer.setAlignment(Qt.AlignCenter)
        self.timer.setFont(font(14, QFont.Bold))
        self.timer.setFixedHeight(26)
        lay.addWidget(self.timer)
        lay.addStretch(2)
        lay.addWidget(shield, alignment=Qt.AlignCenter)
        lay.addStretch(3)

        # connectivity
        self.conn = card()
        cl = QVBoxLayout(self.conn)
        cl.setContentsMargins(14, 10, 14, 12)
        cl.setSpacing(6)
        h = QLabel("Connectivity")
        h.setFont(font(15, QFont.Bold))
        h.setStyleSheet(f"color:{MUTED};")
        cl.addWidget(h)
        for icon, text in (("private", "Secured Private Access"),
                           ("internet", "Secured Internet Access")):
            row = QHBoxLayout()
            row.setSpacing(12)
            ic = QLabel()
            ic.setPixmap(self._badge(icon))
            row.addWidget(ic)
            t = QLabel(text)
            t.setFont(font(13))
            row.addWidget(t, 1)
            cl.addLayout(row)
        lay.addWidget(self.conn)
        lay.addSpacing(8)

        # user
        self.who = card()
        wl = QVBoxLayout(self.who)
        wl.setContentsMargins(14, 10, 14, 10)
        wl.setSpacing(2)
        self.user = QLabel("")
        self.user.setFont(font(17, QFont.DemiBold))
        self.account = QLabel("")
        self.account.setFont(font(13))
        self.pop = QLabel("")
        self.pop.setFont(font(13))
        for w in (self.user, self.account, self.pop):
            wl.addWidget(w)
        lay.addWidget(self.who)

    @staticmethod
    def _badge(icon):
        pm = QPixmap(64, 56)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 6, svg_pixmap(icon, "#9a9a9a", 48, bg=CARD, dpr=1.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(GREEN_HI))
        p.drawEllipse(QPointF(46, 12), 10, 10)
        p.setPen(QPen(QColor("#ffffff"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(41, 12), QPointF(45, 16), QPointF(51, 8)])
        p.end()
        pm.setDevicePixelRatio(2)
        return pm


class Rows(QWidget):
    """Label/value table split into sections."""

    def __init__(self, sections):
        super().__init__()
        self.values = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for i, (title, labels) in enumerate(sections):
            if i:
                lay.addSpacing(26)
            h = QLabel(title)
            h.setFont(font(12, QFont.Bold))
            h.setStyleSheet(f"color:{MUTED};")
            lay.addWidget(h)
            lay.addSpacing(6)
            lay.addWidget(hline())
            for lab in labels:
                row = QHBoxLayout()
                row.setContentsMargins(0, 6, 0, 6)
                l = QLabel(lab)
                l.setFont(font(13))
                v = QLabel("N/A")
                v.setFont(font(13))
                v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                v.setTextInteractionFlags(Qt.TextSelectableByMouse)
                row.addWidget(l)
                row.addWidget(v, 1)
                lay.addLayout(row)
                lay.addWidget(hline())
                self.values[lab] = v

    def set(self, label, value):
        self.values[label].setText(value if value not in (None, "") else "N/A")


def scroll_page(inner):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    sa.setStyleSheet("""QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
        QScrollBar:vertical { background: transparent; width: 8px; }
        QScrollBar::handle:vertical { background: #444; border-radius: 4px; min-height: 30px; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }""")
    return sa


class StatsPage(QWidget):
    def __init__(self):
        super().__init__()
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(30, 34, 30, 24)
        lay.addWidget(page_title("Statistics"))
        lay.addSpacing(4)
        lay.addWidget(hline())
        lay.addSpacing(26)
        self.rows = Rows([
            ("Data Transfer", ["Sent", "Received", "Packets Sent", "Packets Received"]),
            ("Connection Details", ["Local IP", "Tunnel IP", "Connected PoP", "PoP Address",
                                    "Latency to PoP", "Session Start Time", "Last Active",
                                    "Connected via Office", "Tunnel Device", "DNS Servers",
                                    "Type", "Always-On", "Split Tunnel", "DNS Mode",
                                    "Transport"]),
            ("Client", ["Client Version", "SDP Shield Version"]),
            ("User Identity", ["Identity", "Last reported"]),
        ])
        lay.addWidget(self.rows)
        lay.addStretch(1)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll_page(inner))

    def update_from(self, st: Status, settings):
        r = self.rows
        c = st.connected
        r.set("Sent", human_bytes(st.bytes("bio_tx_bytes") if c else 0))
        r.set("Received", human_bytes(st.bytes("bio_rx_bytes") if c else 0))
        r.set("Packets Sent", st.get("tx_packets") if c else "0")
        r.set("Packets Received", st.get("rx_packets") if c else "0")
        r.set("Local IP", st.local_ip if c else "")
        r.set("Tunnel IP", st.get("tunnel ip") if c else "")
        r.set("Connected PoP", st.pop if c else "")
        r.set("PoP Address", st.get("pop address") if c else "")
        rtt = st.rtt if c else None
        r.set("Latency to PoP", f"{rtt[0]} ms (last {rtt[1]} ms)" if rtt else "")
        ss = st.session_start if c else None
        r.set("Session Start Time", ss.strftime("%d/%m/%Y %H:%M") if ss else "")
        la = st.get("last_read_sec") if c else ""
        r.set("Last Active", ("Just now" if la == "00:00:00" else f"{la} ago") if la else "")
        r.set("Connected via Office", "Yes" if st.get("connected_via_office") == "yes" else "No")
        r.set("Tunnel Device", st.get("tun device") if c else "")
        dns = ", ".join(x for x in (st.get("dns1"), st.get("dns2")) if x) if c else ""
        r.set("DNS Servers", dns)
        r.set("Type", "SDP Client" if c else "")
        r.set("Always-On", "Enabled" if settings.get("always_on") else "Disabled")
        r.set("Split Tunnel", settings.get("route") if settings.get("split") else "Disabled")
        r.set("DNS Mode", "systemd-resolved" if settings.get("resolved") else "resolv.conf")
        r.set("Transport", "TCP only" if settings.get("tcp_only") else "UDP + TCP")
        r.set("Client Version", st.client_version)
        r.set("SDP Shield Version", __version__)
        ident = f"{st.user}/{st.account}" if st.user else ""
        r.set("Identity", ident)
        r.set("Last reported", st.when.strftime("%d/%m/%Y %H:%M:%S") if st.raw else "")


class UserRow(QWidget):
    changed = Signal()
    remove = Signal(object)

    def __init__(self, data, radio_group_cb):
        super().__init__()
        self.data = data
        g = QGridLayout(self)
        g.setContentsMargins(0, 8, 0, 8)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(4)
        self.radio = Radio()
        self.radio.clicked.connect(lambda: radio_group_cb(self))
        g.addWidget(self.radio, 0, 0, 2, 1, Qt.AlignTop | Qt.AlignHCenter)
        self.user = QLabel(data.get("user", ""))
        self.user.setFont(font(15, QFont.Bold))
        g.addWidget(self.user, 0, 1, 1, 2)
        self.rm = QPushButton()
        self.rm.setIcon(QIcon(svg_pixmap("close", MUTED, 14, bg=PAGE)))
        self.rm.setFixedSize(26, 26)
        self.rm.setCursor(Qt.PointingHandCursor)
        self.rm.setToolTip("Remove user")
        self.rm.setStyleSheet("QPushButton{border:none;background:transparent;}"
                              "QPushButton:hover{background:#2c2c2c;border-radius:13px;}")
        self.rm.clicked.connect(lambda: self.remove.emit(self))
        g.addWidget(self.rm, 0, 3, Qt.AlignRight)
        self.acc = QLabel(data.get("account", ""))
        self.acc.setFont(font(14))
        g.addWidget(self.acc, 1, 1, 1, 3)
        lab = QLabel("PoP Server IP")
        lab.setFont(font(13))
        lab.setStyleSheet(f"color:{MUTED};")
        g.addWidget(lab, 2, 1)
        self.addr = QLineEdit(data.get("address", ""))
        self.addr.setPlaceholderText("Server Address")
        self.addr.setStyleSheet(f"QLineEdit{{background:{CARD};border:1px solid {LINE};"
                                f"border-radius:6px;padding:5px 8px;color:{TEXT};}}"
                                f"QLineEdit:disabled{{color:{FAINT};}}")
        self.addr.editingFinished.connect(self._save)
        g.addWidget(self.addr, 2, 2)
        self.tg = Toggle()
        self.tg.setChecked(bool(data.get("use_address")))
        self.tg.toggled.connect(self._save)
        g.addWidget(self.tg, 2, 3)
        g.setColumnStretch(2, 1)

    def _save(self, *_):
        self.data["address"] = self.addr.text().strip()
        self.data["use_address"] = self.tg.isChecked()
        self.changed.emit()

    def set_locked(self, locked, selected):
        self.radio.setChecked(selected)
        for w in (self.radio, self.addr, self.tg, self.rm):
            w.setEnabled(not locked)
        self.rm.setVisible(not locked)
        col = (GREEN if locked else GREEN_HI) if selected else (FAINT if locked else TEXT)
        self.user.setStyleSheet(f"color:{col};")
        self.acc.setStyleSheet(f"color:{FAINT if locked else '#cfcfcf'};")


class AddUserDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add User")
        self.setStyleSheet(f"QDialog{{background:{PAGE};}} QLabel{{color:{TEXT};}}"
                           f"QLineEdit{{background:{CARD};border:1px solid {LINE};border-radius:6px;"
                           f"padding:7px 9px;color:{TEXT};}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        t = QLabel("Add User")
        t.setFont(font(22, QFont.Light))
        lay.addWidget(t)
        lay.addSpacing(8)
        self.user = QLineEdit()
        self.user.setPlaceholderText("User (e-mail)")
        self.account = QLineEdit()
        self.account.setPlaceholderText("Account")
        self.address = QLineEdit()
        self.address.setPlaceholderText("PoP Server Address (optional)")
        for w in (self.user, self.account, self.address):
            lay.addWidget(w)
        lay.addSpacing(10)
        row = QHBoxLayout()
        cancel = pill_button("Cancel")
        cancel.clicked.connect(self.reject)
        ok = pill_button("Add")
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.resize(380, 0)

    def _ok(self):
        if self.user.text().strip() and self.account.text().strip():
            self.accept()

    def value(self):
        a = self.address.text().strip()
        return {"user": self.user.text().strip(), "account": self.account.text().strip(),
                "address": a, "use_address": bool(a)}


class UsersPage(QWidget):
    disconnect_requested = Signal()

    def __init__(self):
        super().__init__()
        self.store = load_json("users.json", {"users": [], "selected": -1})
        self.locked = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 34, 30, 24)
        top = QHBoxLayout()
        top.addWidget(page_title("Users"))
        top.addStretch(1)
        self.add = QPushButton("ADD USER")
        self.add.setCursor(Qt.PointingHandCursor)
        self.add.setFixedHeight(40)
        self.add.setStyleSheet(f"""
            QPushButton {{ background:#3a3a3a; color:{TEXT}; border:none; border-radius:20px;
                          font-weight:800; font-size:13px; padding:0 22px; }}
            QPushButton:hover {{ background:#464646; }}
            QPushButton:disabled {{ background:#2c2c2c; color:#777; }}""")
        self.add.clicked.connect(self._add)
        top.addWidget(self.add)
        lay.addLayout(top)
        lay.addSpacing(22)
        self.banner = QPushButton("Disconnect to edit users")
        self.banner.setCursor(Qt.PointingHandCursor)
        self.banner.setFixedHeight(40)
        self.banner.setStyleSheet(f"""
            QPushButton {{ border:1.5px solid #e8e8e8; border-radius:20px; color:{TEXT};
                          background:transparent; font-size:14px; }}
            QPushButton:hover {{ background:#2a2a2a; }}""")
        self.banner.clicked.connect(self.disconnect_requested)
        lay.addWidget(self.banner)
        lay.addSpacing(12)
        self.listw = QWidget()
        self.listl = QVBoxLayout(self.listw)
        self.listl.setContentsMargins(0, 0, 0, 0)
        self.listl.setSpacing(6)
        lay.addWidget(scroll_page(self.listw), 1)
        self.empty = QLabel("No users yet. Connect once or press ADD USER.")
        self.empty.setStyleSheet(f"color:{MUTED};")
        self.empty.setAlignment(Qt.AlignCenter)
        self.rows = []
        self._rebuild()

    # data
    def selected(self):
        i = self.store.get("selected", -1)
        users = self.store["users"]
        return users[i] if 0 <= i < len(users) else None

    def learn(self, user, account):
        """Add the user reported by the client, if it is new."""
        if not user:
            return
        for i, u in enumerate(self.store["users"]):
            if u["user"].lower() == user.lower() and u["account"].lower() == account.lower():
                if self.store.get("selected", -1) < 0:
                    self.store["selected"] = i
                    self._persist()
                return
        self.store["users"].append({"user": user, "account": account,
                                    "address": "", "use_address": False})
        if self.store.get("selected", -1) < 0:
            self.store["selected"] = len(self.store["users"]) - 1
        self._persist()
        self._rebuild()

    def _persist(self):
        save_json("users.json", self.store)

    # UI
    def _rebuild(self):
        while self.listl.count():
            it = self.listl.takeAt(0)
            if it.widget() is not None:
                it.widget().setParent(None)
        self.rows = []
        for u in self.store["users"]:
            r = UserRow(u, self._select)
            r.changed.connect(self._persist)
            r.remove.connect(self._remove)
            self.listl.addWidget(r)
            self.rows.append(r)
        if not self.rows:
            self.listl.addWidget(self.empty)
        self.listl.addStretch(1)
        self.set_locked(self.locked)

    def _select(self, row):
        self.store["selected"] = self.rows.index(row)
        self._persist()
        self.set_locked(self.locked)

    def _remove(self, row):
        i = self.rows.index(row)
        if QMessageBox.question(self, "Remove user",
                                f"Remove {row.data['user']} from the list?") != QMessageBox.Yes:
            return
        del self.store["users"][i]
        sel = self.store.get("selected", -1)
        self.store["selected"] = -1 if sel == i else (sel - 1 if sel > i else sel)
        self._persist()
        self._rebuild()

    def _add(self):
        d = AddUserDialog(self.window())
        if d.exec():
            self.store["users"].append(d.value())
            self.store["selected"] = len(self.store["users"]) - 1
            self._persist()
            self._rebuild()

    def set_locked(self, locked):
        self.locked = locked
        self.banner.setVisible(locked)
        self.add.setEnabled(not locked)
        sel = self.store.get("selected", -1)
        for i, r in enumerate(self.rows):
            r.set_locked(locked, i == sel)


class SettingsPage(QWidget):
    changed = Signal()

    DEFAULTS = {"autostart": os.path.exists(AUTOSTART), "always_on": False,
                "connect_on_start": False, "resolved": False, "tcp_only": False,
                "split": False, "route": "", "notifications": True}

    def __init__(self):
        super().__init__()
        self.s = {**self.DEFAULTS, **load_json("settings.json", {})}
        self.s["autostart"] = os.path.exists(AUTOSTART)
        check = write_check_svg()
        self.setStyleSheet(f"""
            QCheckBox {{ color:{TEXT}; font-size:15px; spacing:12px; }}
            QCheckBox:disabled {{ color:{FAINT}; }}
            QCheckBox::indicator {{ width:20px; height:20px; border-radius:6px; background:#2c2c2c; }}
            QCheckBox::indicator:checked {{ background:{GREEN}; image:url({check}); }}
            QCheckBox::indicator:disabled {{ background:#262626; }}
            QCheckBox::indicator:checked:disabled {{ background:#2f4a3c; }}
            QLineEdit {{ background:{CARD}; border:1px solid {LINE}; border-radius:6px;
                         padding:5px 8px; color:{TEXT}; }}
            QLineEdit:disabled {{ color:{FAINT}; }}""")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 34, 30, 24)
        lay.setSpacing(0)
        lay.addWidget(page_title("Settings"))
        lay.addSpacing(26)
        note = QLabel("Some settings can only be changed when SDP is not connected")
        note.setFont(font(12, QFont.Medium))
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addSpacing(16)

        self.boxes = {}
        spec = [
            ("autostart", "Start at login", False,
             "Open this app automatically when you log in"),
            ("connect_on_start", "Connect when the app starts", False,
             "Connect automatically as soon as the app is opened"),
            ("always_on", "Always-On (reconnect if the link drops)", False,
             "Reconnect automatically when the tunnel drops without you asking"),
            ("resolved", "Use systemd-resolved for DNS", True,
             "cato-sdp start --use-systemd-resolv"),
            ("tcp_only", "TCP only (restrictive networks)", True,
             "cato-sdp start --tcp 2"),
            ("split", "Split Tunnel", True,
             "Route only this CIDR through the tunnel (cato-sdp start --route)"),
        ]
        self.locked_keys = []
        for key, label, locked, tip in spec:
            cb = QCheckBox(label)
            cb.setToolTip(tip)
            cb.setCursor(Qt.PointingHandCursor)
            cb.setChecked(bool(self.s.get(key)))
            cb.toggled.connect(lambda v, k=key: self._set(k, v))
            lay.addWidget(cb)
            lay.addSpacing(14)
            self.boxes[key] = cb
            if locked:
                self.locked_keys.append(key)
        self.route = QLineEdit(self.s.get("route", ""))
        self.route.setPlaceholderText("e.g. 10.0.0.0/8")
        self.route.setContentsMargins(32, 0, 0, 0)
        self.route.editingFinished.connect(lambda: self._set("route", self.route.text().strip()))
        lay.addWidget(self.route)
        lay.addSpacing(18)
        lay.addWidget(hline())
        lay.addSpacing(18)
        row = QHBoxLayout()
        l = QLabel("System Notifications:")
        l.setFont(font(15))
        l.setStyleSheet(f"color:{MUTED};")
        row.addWidget(l)
        self.notif = QPushButton()
        self.notif.setCursor(Qt.PointingHandCursor)
        self.notif.setFont(font(15, QFont.Bold))
        self.notif.setStyleSheet(f"QPushButton{{border:none;background:transparent;color:{TEXT};"
                                 f"text-align:left;padding:0 6px;}} QPushButton:hover{{color:{GREEN_HI};}}")
        self.notif.setToolTip("Click to switch")
        self.notif.clicked.connect(lambda: self._set("notifications", not self.s["notifications"]))
        row.addWidget(self.notif)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self._refresh()

    def _set(self, key, value):
        self.s[key] = value
        if key == "autostart":
            self._autostart(value)
        save_json("settings.json", {k: v for k, v in self.s.items() if k != "autostart"})
        self._refresh()
        self.changed.emit()

    @staticmethod
    def _autostart(on):
        if on:
            os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
            with open(AUTOSTART, "w") as f:
                f.write(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\n"
                        f"Exec={APP_ID} --hidden\nIcon={APP_ID}\n"
                        "X-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(AUTOSTART):
            os.remove(AUTOSTART)

    def _refresh(self):
        self.notif.setText("Allowed" if self.s["notifications"] else "Off")
        self.route.setVisible(bool(self.s["split"]))

    def set_locked(self, locked):
        for k in self.locked_keys:
            self.boxes[k].setEnabled(not locked)
        self.route.setEnabled(not locked)

    def start_args(self):
        a = []
        if self.s.get("resolved"):
            a.append("--use-systemd-resolv")
        if self.s.get("tcp_only"):
            a += ["--tcp", "2"]
        if self.s.get("split") and self.s.get("route"):
            a += ["--route", self.s["route"]]
        return a


class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 70, 20, 20)
        lay.addWidget(Wordmark("#ffffff", 76))
        lay.addSpacing(18)
        self.version = QLabel("")
        self.version.setFont(font(18))
        self.version.setStyleSheet("color:#cfcfcf;")
        self.version.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.version)
        self.gui = QLabel(f"{APP_NAME} {__version__}\nUnofficial front-end, not affiliated with "
                          "Cato Networks")
        self.gui.setFont(font(12))
        self.gui.setStyleSheet(f"color:{FAINT};")
        self.gui.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.gui)
        lay.addStretch(1)

    def set_version(self, v):
        self.version.setText(f"Client version {v}" if v else "Client version —")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # large outlined shield, partly off the page
        sw = w * 0.95
        sh = shield_path(w * 0.42, h * 0.48, sw, sw * 1.2)
        p.setBrush(Qt.NoBrush)
        g = QLinearGradient(w * 0.42, h * 0.48, w, h)
        g.setColorAt(0, QColor(242, 242, 243, 70))
        g.setColorAt(1, QColor(160, 162, 166, 25))
        p.setPen(QPen(g, w * 0.11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(sh)
        p.end()


class SupportPage(QWidget):
    def __init__(self, get_status):
        super().__init__()
        self.get_status = get_status
        self.rec = None          # (start time, {file: size})
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 34, 30, 24)
        lay.setSpacing(0)
        lay.addWidget(page_title("Support"))
        lay.addSpacing(26)

        def section(title, text, button):
            h = QLabel(title)
            h.setFont(font(18, QFont.Bold))
            h.setStyleSheet("color:#dedede;")
            lay.addWidget(h)
            lay.addSpacing(14)
            t = QLabel(text)
            t.setWordWrap(True)
            t.setFont(font(14))
            t.setStyleSheet("color:#cfcfcf;")
            lay.addWidget(t)
            lay.addSpacing(20)
            row = QHBoxLayout()
            row.addStretch(1)
            button.setFixedWidth(200)
            row.addWidget(button)
            lay.addLayout(row)

        self.record = pill_button("Record Issue")
        self.record.clicked.connect(self._record)
        section("Record Client Issues",
                "If you experience an issue with the Client, record data while "
                "replicating the issue and send it to support", self.record)
        lay.addSpacing(22)
        lay.addWidget(hline())
        lay.addSpacing(22)
        self.download = pill_button("Download Logs")
        self.download.clicked.connect(self._download)
        section("Download Logs",
                "You can download logs to support the troubleshooting of issues", self.download)
        lay.addSpacing(18)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setFont(font(12))
        self.info.setStyleSheet(f"color:{MUTED};")
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.info)
        lay.addStretch(1)

    @staticmethod
    def _logs():
        out = []
        if os.path.isdir(CLIENT_DIR):
            for n in os.listdir(CLIENT_DIR):
                if n.startswith("cato-sdp.log"):
                    out.append(os.path.join(CLIENT_DIR, n))
        return out

    def _ask_path(self, name):
        d = os.path.join(HOME_DIR, "Downloads")
        path, _ = QFileDialog.getSaveFileName(self, "Save", os.path.join(
            d if os.path.isdir(d) else HOME_DIR, name))
        return path

    def _record(self):
        if self.rec is None:
            self.rec = (dt.datetime.now(),
                        {f: os.path.getsize(f) for f in self._logs()})
            self.record.setText("Stop Recording")
            self.info.setText("Recording… reproduce the issue, then press Stop Recording.")
            return
        start, sizes = self.rec
        self.rec = None
        self.record.setText("Record Issue")
        stamp = start.strftime("%Y%m%d-%H%M%S")
        path = self._ask_path(f"cato-issue-{stamp}.txt")
        if not path:
            self.info.setText("Recording discarded.")
            return
        main = os.path.join(CLIENT_DIR, "cato-sdp.log")
        parts = []
        try:
            cur = os.path.getsize(main)
            before = sizes.get(main, 0)
            if cur < before:                       # the log rotated while recording
                rot = main + ".1"
                with open(rot, errors="replace") as f:
                    f.seek(before)
                    parts.append(f.read())
                before = 0
            with open(main, errors="replace") as f:
                f.seek(before)
                parts.append(f.read())
        except OSError as exc:
            parts.append(f"[could not read log: {exc}]")
        st = self.get_status()
        with open(path, "w") as f:
            f.write(f"{APP_NAME} issue recording\nfrom {start:%Y-%m-%d %H:%M:%S} "
                    f"to {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
            f.write("=== status at stop ===\n" + (st.raw or "n/a") + "\n\n")
            f.write("=== cato-sdp.log during recording ===\n" + "".join(parts))
        self.info.setText(f"Saved: {path}")

    def _download(self):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self._ask_path(f"cato-logs-{stamp}.tar.gz")
        if not path:
            return
        st = self.get_status()

        def job():
            with tarfile.open(path, "w:gz") as tar:
                for f in self._logs():               # never the credential files (cato_cred.cfg*)
                    tar.add(f, arcname=os.path.join("cato-logs", os.path.basename(f)))
                extra = os.path.join(CACHE_DIR, "status.txt")
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(extra, "w") as f:
                    f.write(st.raw or "")
                    _, v = run("version")
                    f.write("\n\n" + v + "\n")
                    try:
                        j = subprocess.run(["journalctl", "-u", "cato-client", "-n", "2000",
                                            "--no-pager"], capture_output=True, text=True,
                                           timeout=20).stdout
                        f.write("\n=== journalctl -u cato-client ===\n" + j)
                    except Exception:
                        pass
                tar.add(extra, arcname="cato-logs/status.txt")
            return path

        self.download.setEnabled(False)
        self.info.setText("Collecting logs…")
        self._job = Job(job)
        self._job.done.connect(self._downloaded)
        self._job.start()

    def _downloaded(self, ok, msg):
        self.download.setEnabled(True)
        self.info.setText(f"Saved: {msg}" if ok else f"Error: {msg}")


class FeedbackDialog(QDialog):
    TOPICS = ["Initiate Connectivity", "Connection Stability", "Internet Speed",
              "Download/Upload Files", "Ease of Use", "Other"]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Share Your Feedback")
        self.setStyleSheet(f"QDialog{{background:{PAGE};}} QLabel{{color:{TEXT};}}")
        self.rating = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        top = QHBoxLayout()
        t = QLabel("Share Your Feedback")
        t.setFont(font(26, QFont.Light))
        top.addWidget(t)
        top.addStretch(1)
        x = QPushButton()
        x.setIcon(QIcon(svg_pixmap("close", "#bbbbbb", 22, bg=PAGE)))
        x.setIconSize(QSize(22, 22))
        x.setFixedSize(32, 32)
        x.setCursor(Qt.PointingHandCursor)
        x.setStyleSheet("QPushButton{border:none;background:transparent;}")
        x.clicked.connect(self.reject)
        top.addWidget(x)
        lay.addLayout(top)
        lay.addSpacing(18)
        r = QLabel("Rate your experience")
        r.setFont(font(14))
        r.setAlignment(Qt.AlignCenter)
        lay.addWidget(r)
        stars = QHBoxLayout()
        stars.addStretch(1)
        self.stars = []
        for i in range(5):
            b = QPushButton("☆")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(46, 46)
            b.clicked.connect(lambda _=False, n=i + 1: self._rate(n))
            stars.addWidget(b)
            self.stars.append(b)
        stars.addStretch(1)
        lay.addLayout(stars)
        lay.addSpacing(14)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Tell us some more")
        self.text.setFixedHeight(150)
        self.text.setStyleSheet(f"QPlainTextEdit{{background:{CARD};border:1.5px solid #6a6a6a;"
                                f"border-radius:12px;padding:8px;color:{TEXT};font-size:14px;}}")
        self.text.textChanged.connect(self._count)
        lay.addWidget(self.text)
        self.counter = QLabel("0/240")
        self.counter.setAlignment(Qt.AlignRight)
        self.counter.setStyleSheet(f"color:{MUTED};font-size:11px;")
        lay.addWidget(self.counter)
        lay.addSpacing(10)
        rel = QLabel("My feedback is related to…")
        rel.setFont(font(14))
        lay.addWidget(rel)
        lay.addSpacing(6)
        self.chips = []
        for chunk in (self.TOPICS[:3], self.TOPICS[3:]):
            row = QHBoxLayout()
            row.setSpacing(10)
            for topic in chunk:
                c = QPushButton(topic)
                c.setCheckable(True)
                c.setCursor(Qt.PointingHandCursor)
                c.setFixedHeight(34)
                c.setStyleSheet(f"""
                    QPushButton {{ border:1.5px solid #9a9a9a; border-radius:17px; color:{TEXT};
                                  background:transparent; padding:0 14px; font-size:13px; }}
                    QPushButton:checked {{ border-color:{GREEN_HI}; background:rgba(27,122,80,0.35); }}""")
                row.addWidget(c)
                self.chips.append(c)
            row.addStretch(1)
            lay.addLayout(row)
        lay.addSpacing(16)
        self.send = QPushButton("Send")
        self.send.setFixedSize(220, 46)
        self.send.setCursor(Qt.PointingHandCursor)
        self.send.setStyleSheet(f"""
            QPushButton {{ background:{GREEN}; color:white; border:none; border-radius:23px;
                          font-weight:700; font-size:15px; }}
            QPushButton:disabled {{ background:#505050; color:#e0e0e0; }}""")
        self.send.clicked.connect(self._send)
        self.send.setEnabled(False)
        lay.addWidget(self.send, alignment=Qt.AlignCenter)
        lay.addSpacing(12)
        foot = QLabel("For help or to report an issue, contact your IT department")
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet(f"color:{MUTED};font-size:13px;")
        lay.addWidget(foot)
        self._rate(0)
        self.resize(520, 0)

    def _rate(self, n):
        self.rating = n
        for i, b in enumerate(self.stars):
            on = i < n
            b.setText("★" if on else "☆")
            b.setStyleSheet(f"QPushButton{{border:none;background:transparent;font-size:34px;"
                            f"color:{GREEN_HI if on else GREEN_DK};}}"
                            f"QPushButton:hover{{color:{GREEN_HI};}}")
        self.send.setEnabled(n > 0)

    def _count(self):
        t = self.text.toPlainText()
        if len(t) > 240:
            self.text.setPlainText(t[:240])
            c = self.text.textCursor()
            c.movePosition(c.MoveOperation.End)
            self.text.setTextCursor(c)
            return
        self.counter.setText(f"{len(t)}/240")

    def _send(self):
        entry = {"when": dt.datetime.now().isoformat(timespec="seconds"),
                 "rating": self.rating, "text": self.text.toPlainText(),
                 "topics": [c.text() for c in self.chips if c.isChecked()]}
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "feedback.log"), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        txt = (f"{APP_NAME} feedback ({entry['when']})\nRating: {'★' * self.rating}"
               f"{'☆' * (5 - self.rating)}\nTopics: {', '.join(entry['topics']) or '-'}\n\n"
               f"{entry['text']}")
        QApplication.clipboard().setText(txt)
        QMessageBox.information(self, "Feedback",
                                "Thank you! Feedback saved and copied to the clipboard,\n"
                                "ready to paste in a message to your IT department.")
        self.accept()


# --------------------------------------------------------------------------- window

class NavButton(QPushButton):
    def __init__(self, icon, label):
        super().__init__()
        self.icon_name, self.label = icon, label
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(20, 20))
        self.setIcon(QIcon(svg_pixmap(icon, "#ffffff", 20)))
        self.setFont(font(15))
        self.setStyleSheet(f"""
            QPushButton {{ border:none; border-radius:8px; color:{TEXT}; background:transparent;
                          text-align:left; padding-left:9px; }}
            QPushButton:hover {{ background:#262626; }}
            QPushButton:checked {{ background:{GREEN}; }}""")
        self.set_compact(False)

    def set_compact(self, compact):
        self.setText("" if compact else f"  {self.label}")
        self.setToolTip(self.label if compact else "")


class TrafficLights(QWidget):
    close_clicked = Signal()
    min_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(66, 20)
        self.hover = False
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, _):
        self.hover = True
        self.update()

    def leaveEvent(self, _):
        self.hover = False
        self.update()

    def mousePressEvent(self, ev):
        x = ev.position().x()
        if x < 20:
            self.close_clicked.emit()
        elif x < 42:
            self.min_clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i, col in enumerate(("#ff5f57", "#febc2e", "#3d3d3d")):
            cx = 7 + i * 22
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(cx, 10), 7, 7)
            if self.hover and i < 2:
                p.setPen(QPen(QColor(0, 0, 0, 150), 1.4, Qt.SolidLine, Qt.RoundCap))
                if i == 0:
                    p.drawLine(QPointF(cx - 3, 7), QPointF(cx + 3, 13))
                    p.drawLine(QPointF(cx + 3, 7), QPointF(cx - 3, 13))
                else:
                    p.drawLine(QPointF(cx - 3.5, 10), QPointF(cx + 3.5, 10))
        p.end()


class Root(QWidget):
    """Rounded background of the frameless window."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 16, 16)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor(PAGE))
        sb = self.property("sidebar_w") or 150
        p.fillRect(QRectF(0, 0, sb, self.height()), QColor(SIDEBAR))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        p.end()


def make_icon(connected):
    """Tray icon: small shield with a white dot, green when connected, grey otherwise."""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 2, 0, size - 2)
    if connected:
        g.setColorAt(0, QColor(GREEN_HI))
        g.setColorAt(1, QColor(GREEN))
    else:
        g.setColorAt(0, QColor("#9aa0a6"))
        g.setColorAt(1, QColor("#6b7075"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(shield_path(8, 3, size - 16, size - 6))
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(size / 2, size * 0.46), size * 0.13, size * 0.13)
    p.end()
    return QIcon(pm)


class Window(QMainWindow):
    SIDEBAR_W, SIDEBAR_COMPACT = 150, 58

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(540, 700)
        self.busy = False
        self.user_stopped = False
        self.status = Status()
        self.first_poll = True
        self.last_reconnect = None
        self.seconds = 0

        self.shield = Shield()
        self.shield.clicked.connect(self.toggle)
        self.home = HomePage(self.shield)
        self.stats = StatsPage()
        self.users = UsersPage()
        self.users.disconnect_requested.connect(self.disconnect)
        self.settings = SettingsPage()
        self.settings.changed.connect(lambda: self.stats.update_from(self.status, self.settings.s))
        self.about = AboutPage()
        self.support = SupportPage(lambda: self.status)

        self.pages = QStackedWidget()
        for w in (self.home, self.stats, self.users, self.settings, self.about, self.support):
            self.pages.addWidget(w)
        self.pages.setStyleSheet(f"QLabel {{ color:{TEXT}; background:transparent; }}")

        # sidebar
        self.bar = QWidget()
        self.bar.setFixedWidth(self.SIDEBAR_W)
        bl = QVBoxLayout(self.bar)
        bl.setContentsMargins(10, 14, 10, 14)
        bl.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 0, 0)
        self.lights = TrafficLights()
        self.lights.close_clicked.connect(self.close)
        self.lights.min_clicked.connect(self.showMinimized)
        top.addWidget(self.lights)
        top.addStretch(1)
        self.fold = QPushButton()
        self.fold.setIcon(QIcon(svg_pixmap("sidebar", "#e6e6e6", 20)))
        self.fold.setIconSize(QSize(20, 20))
        self.fold.setFixedSize(34, 34)
        self.fold.setCursor(Qt.PointingHandCursor)
        self.fold.setToolTip("Show/hide sidebar")
        self.fold.setStyleSheet("QPushButton{background:#2a2a2a;border:1px solid #3a3a3a;"
                                "border-radius:17px;} QPushButton:hover{background:#333;}")
        self.fold.clicked.connect(self.fold_sidebar)
        top.addWidget(self.fold)
        self.top_row = top
        bl.addLayout(top)
        bl.addSpacing(14)
        self.buttons = []
        for i, (icon, label) in enumerate((("home", "Home"), ("stats", "Statistics"),
                                           ("users", "Users"), ("settings", "Settings"),
                                           ("about", "About"), ("support", "Support"))):
            b = NavButton(icon, label)
            b.clicked.connect(lambda _=False, n=i: self.go(n))
            bl.addWidget(b)
            self.buttons.append(b)
        bl.addStretch(1)
        self.fb = NavButton("feedback", "Feedback")
        self.fb.setCheckable(False)
        self.fb.clicked.connect(lambda: FeedbackDialog(self).exec())
        bl.addWidget(self.fb)
        self.buttons[0].setChecked(True)
        self.compact = False

        root = Root()
        root.setProperty("sidebar_w", self.SIDEBAR_W)
        self.root = root
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.bar)
        rl.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        # tray
        self.tray = QSystemTrayIcon(make_icon(False), self)
        menu = QMenu()
        self.act_toggle = QAction("Connect", self)
        self.act_toggle.triggered.connect(self.toggle)
        act_show = QAction("Show window", self)
        act_show.triggered.connect(self.bring_up)
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(self.act_toggle)
        menu.addSeparator()
        menu.addAction(act_show)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.bring_up() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        QTimer.singleShot(0, self.tray.show)
        QTimer.singleShot(2500, self.tray.show)

        _, ver = run("version")
        m = re.search(r"Client:\s*(\S+)", ver)
        self.about.set_version(m.group(1) if m else ver.strip())

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(3000)
        self.tick = QTimer(self)
        self.tick.timeout.connect(self.bump)
        self.tick.start(1000)
        self.refresh()

    # navigation / window
    def go(self, n):
        for i, b in enumerate(self.buttons):
            b.setChecked(i == n)
        self.pages.setCurrentIndex(n)

    def fold_sidebar(self):
        self.compact = not self.compact
        w = self.SIDEBAR_COMPACT if self.compact else self.SIDEBAR_W
        self.bar.setFixedWidth(w)
        self.root.setProperty("sidebar_w", w)
        self.lights.setVisible(not self.compact)
        for b in self.buttons + [self.fb]:
            b.set_compact(self.compact)
        self.setFixedSize(540 - (self.SIDEBAR_W - w), 700)
        self.root.update()

    def bring_up(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    # status
    def bump(self):
        if self.status.connected and self.status.duration:
            self.seconds += 1
            m = re.match(r"(\d+):(\d\d):(\d\d)", self.status.duration)
            if m:
                h, mi, s = map(int, m.groups())
                t = h * 3600 + mi * 60 + s + self.seconds
                self.home.timer.setText(f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}")

    def refresh(self):
        if not self.tray.isVisible():
            self.tray.show()
        p = getattr(self, "_p", None)
        if p is not None and p.isRunning():          # never replace a running thread
            return
        self._p = Poller()
        self._p.got.connect(self.apply)
        self._p.start()

    def notify(self, text):
        if self.settings.s.get("notifications"):
            self.tray.showMessage(APP_NAME, text, make_icon(True), 4000)

    def apply(self, st: Status):
        prev = self.status
        self.status = st
        self.seconds = 0
        if st.user:
            self.users.learn(st.user, st.account)

        if st.connected and not prev.connected and not self.first_poll:
            self.notify("Connected" + (f" to {st.pop}" if st.pop else ""))
        if prev.connected and not st.connected and not st.connecting:
            if not self.user_stopped:
                self.notify("Disconnected")
                if self.settings.s.get("always_on"):
                    QTimer.singleShot(3000, self.auto_reconnect)
        if self.first_poll:
            self.first_poll = False
            if self.settings.s.get("connect_on_start") and not st.connected \
                    and not st.connecting and st.daemon_ok:
                self.connect_()

        connecting = self.busy or st.connecting
        h = self.home
        if connecting:
            text, col = ("Disconnecting" if self.busy and prev.connected else "Connecting"), TEXT
        elif st.connected:
            text, col = "Connected", GREEN
        else:
            text, col = st.text, (TEXT if st.daemon_ok else MUTED)
        h.status.setText(text)
        h.status.setStyleSheet(f"color:{col};")
        h.timer.setText(st.duration if st.connected and not connecting else "")
        h.conn.setVisible(st.connected and not connecting)
        sel = self.users.selected() or {}
        user = st.user or sel.get("user", "")
        account = st.account or sel.get("account", "")
        h.user.setText(user)
        h.account.setText(account)
        h.pop.setText(f"PoP: {st.pop}" if st.connected and st.pop else "")
        h.pop.setVisible(bool(h.pop.text()))
        h.who.setVisible(bool(user))
        if not st.daemon_ok:
            h.user.setText("The client daemon is not responding")
            h.account.setText("sudo systemctl enable --now cato-client.service")
            h.who.setVisible(True)

        self.shield.set_state("busy" if connecting else ("on" if st.connected else "off"))
        locked = st.connected or connecting
        self.users.set_locked(locked)
        self.settings.set_locked(locked)
        self.stats.update_from(st, self.settings.s)
        if st.client_version:
            self.about.set_version(st.client_version)
        self.tray.setIcon(make_icon(st.connected))
        self.tray.setToolTip(f"{APP_NAME} — {st.text}")
        self.act_toggle.setText("Disconnect" if st.connected else "Connect")

    # actions
    def start_args(self):
        args = ["start"] + self.settings.start_args()
        sel = self.users.selected()
        if sel:
            last = self.settings.s.get("last_user")
            key = f"{sel['user']}|{sel['account']}"
            if last and last != key:                  # user switched: tell the client
                args += ["--user", sel["user"], "--account", sel["account"]]
            if sel.get("use_address") and sel.get("address"):
                args += ["--address", sel["address"]]
        return args

    def _run(self, args):
        if self.busy:
            return
        a = getattr(self, "_a", None)
        if a is not None and a.isRunning():
            return
        self.busy = True
        self.apply(self.status)
        self._a = Action(args)
        self._a.done.connect(self.finished)
        self._a.start()

    def connect_(self):
        self.user_stopped = False
        sel = self.users.selected()
        if sel:
            self.settings.s["last_user"] = f"{sel['user']}|{sel['account']}"
        self._run(self.start_args())
        if sel:
            save_json("settings.json", {k: v for k, v in self.settings.s.items()
                                        if k != "autostart"})

    def disconnect(self):
        self.user_stopped = True
        self._run(["stop"])

    def toggle(self):
        if self.status.connected or self.status.connecting:
            self.disconnect()
        else:
            self.connect_()

    def auto_reconnect(self):
        if self.status.connected or self.busy or self.user_stopped:
            return
        now = dt.datetime.now()
        if self.last_reconnect and (now - self.last_reconnect).total_seconds() < 30:
            QTimer.singleShot(30000, self.auto_reconnect)
            return
        self.last_reconnect = now
        self.connect_()

    def finished(self, ok, out):
        self.busy = False
        if not ok and out:
            self.notify(out.splitlines()[-1][:120])
        self.refresh()

    def shutdown(self):
        """On quit: stop timers and wait for threads, otherwise Qt aborts."""
        self.poll.stop()
        self.tick.stop()
        for t in (getattr(self, "_p", None), getattr(self, "_a", None),
                  getattr(self.support, "_job", None)):
            if t is not None and t.isRunning():
                t.wait(20000)

    def closeEvent(self, ev):
        # the close button hides to the tray: quit only from "Quit"
        ev.ignore()
        if self.tray.isVisible() or QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()
        if not getattr(self, "_warned", False):
            self._warned = True
            self.tray.showMessage(APP_NAME,
                                  "SDP Shield keeps running in the system tray.",
                                  QSystemTrayIcon.Information, 4000)


def snapshot(w, outdir):
    """Debug aid: save one PNG per page (SDP_SHIELD_SNAPSHOT=directory)."""
    os.makedirs(outdir, exist_ok=True)
    names = ["home", "stats", "users", "settings", "about", "support"]

    def shoot(i=0):
        if i < len(names):
            w.go(i)
            QTimer.singleShot(400, lambda: (w.grab().save(os.path.join(outdir, names[i] + ".png")),
                                            shoot(i + 1)))
        else:
            d = FeedbackDialog(w)
            d.show()
            QTimer.singleShot(400, lambda: (d.grab().save(os.path.join(outdir, "feedback.png")),
                                            QApplication.quit()))
    QTimer.singleShot(2500, shoot)


def main():
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {__version__}")
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    crash = open(os.path.join(STATE_DIR, "crash.log"), "a")
    faulthandler.enable(crash)

    def hook(t, v, tb):
        crash.write("".join(traceback.format_exception(t, v, tb)))
        crash.flush()
    sys.excepthook = hook

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)                  # Wayland app_id matches the .desktop file
    app.setWindowIcon(QIcon.fromTheme(APP_ID, make_icon(False)))
    app.setQuitOnLastWindowClosed(False)
    app.setFont(font(13))

    snap = os.environ.get("SDP_SHIELD_SNAPSHOT")
    if not snap:
        SOCK = f"{APP_ID}-single-instance"
        probe = QLocalSocket()
        probe.connectToServer(SOCK)
        if probe.waitForConnected(300):
            probe.write(b"show")
            probe.waitForBytesWritten(300)
            probe.disconnectFromServer()
            sys.exit(0)
        QLocalServer.removeServer(SOCK)             # stale socket left by a crash
        server = QLocalServer()
        server.listen(SOCK)

    w = Window()
    app.aboutToQuit.connect(w.shutdown)
    if snap:
        w.show()
        snapshot(w, snap)
        sys.exit(app.exec())

    def on_second_instance():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.deleteLater()
        w.bring_up()
    server.newConnection.connect(on_second_instance)

    if "--hidden" not in sys.argv:
        w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
