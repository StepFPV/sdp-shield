#!/usr/bin/env python3
"""SDP Shield: unofficial graphical front-end for the Cato Networks Linux client.

It only runs the `cato-sdp` command line tool (status, start, stop, version)
and shows the result. It never reads credentials and opens no network
connections of its own.
"""

import faulthandler
import math
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRectF, QPointF
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient, QPolygonF)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QPushButton, QStackedWidget,
                               QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget)

__version__ = "1.0.0"

APP_NAME = "SDP Shield"
APP_ID = "sdp-shield"
CMD = "cato-sdp"
NOT_FOUND_MSG = f"'{CMD}' was not found. Is the Cato client installed?"

SIDEBAR_BG = "#23232e"
SIDEBAR_FG = "#c9c9d4"
SIDEBAR_ACTIVE = "#ffffff"
PAGE_BG = "#f4f4f6"
GREEN = "#0f7a45"
GREEN_LIGHT = "#19a35c"
RED = "#b23b3b"
GREY = "#8b8b96"
AMBER = "#c58a1a"
DARK = "#1f1f28"


def run(*args, timeout=15):
    """Run cato-sdp and return (ok, output without ANSI colour codes)."""
    try:
        p = subprocess.run([CMD, *args], capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        out = re.sub(r"\x1b\[[0-9;]*m", "", out).strip()
        return p.returncode == 0, out
    except FileNotFoundError:
        return False, NOT_FOUND_MSG
    except subprocess.TimeoutExpired:
        return False, "The command timed out."
    except Exception as exc:                                  # pragma: no cover
        return False, f"Error: {exc}"


@dataclass
class Status:
    connected: bool = False
    connecting: bool = False
    daemon_ok: bool = True
    uptime: str = ""
    name: str = ""
    account: str = ""
    pop: str = ""
    raw: str = ""

    @property
    def text(self):
        if self.connecting:
            return "Connecting…"
        if not self.daemon_ok:
            return "Daemon not running"
        return "Connected" if self.connected else "Disconnected"

    @property
    def color(self):
        if self.connecting:
            return AMBER
        if not self.daemon_ok:
            return GREY
        return GREEN if self.connected else RED


def parse_status(ok, raw):
    """Parse the output of `cato-sdp status`, tolerating format variants."""
    s = Status(raw=raw)
    low = raw.lower()

    # The daemon is alive but busy with the handshake, and reports it this way.
    if "failed to deserialize cmd" in low:
        s.connecting = True
        return s
    if re.search(r"connected_unauth|authentication is now in progress|\bconnecting\b", low):
        s.connecting = True
        return s
    if "failed to connect to cato client daemon" in low or "cannot open pipe" in low:
        s.daemon_ok = False
        return s
    if NOT_FOUND_MSG in raw or "not installed" in low:
        s.daemon_ok = False
        return s

    # Format seen with client 5.8.1:
    #   disconnected -> "Cato client is disconnected"
    #   connected    -> key = value block containing "state = STATE_AUTHENTICATED"
    if "state_authenticated" in low or re.search(r"cato client is connected", low):
        s.connected = True
    elif "state_connected_unauth" in low or "state_connecting" in low:
        s.connecting = True
        return s
    elif re.search(r"cato client is disconnected", low):
        s.connected = False
    else:
        s.connected = bool(re.search(r"\bconnected\b", low)) and not re.search(
            r"\b(disconnected|not connected)\b", low)

    def grab(*keys):
        for k in keys:
            # "Key: value"  or  "Key = value"
            m = re.search(rf"^\s*{k}\s*[:=]\s*(.+?)\s*$", raw, re.I | re.M)
            if m and m.group(1).strip():
                return m.group(1).strip().strip('"')
            # "Key [VALUE]"
            m = re.search(rf"^\s*{k}\s*\[(.+?)\]\s*$", raw, re.I | re.M)
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""

    s.uptime = grab("duration", "uptime", "connected since", "connection time")
    s.name = grab("user", "site name", "site", "profile", "vpn name")
    acc = grab("account", "tenant", "organization", "customer")
    s.account = f"Account: {acc}" if acc else ""
    pop = grab("pop name", "pop", "server", "gateway")
    tip = grab("tunnel ip")
    s.pop = (pop + (f"  ·  {tip}" if tip else "")) if pop else ""
    return s


class Poller(QThread):
    """Query the status without blocking the interface."""
    got = Signal(object)

    def run(self):
        ok, raw = run("status")
        self.got.emit(parse_status(ok, raw))


class Action(QThread):
    done = Signal(bool, str)

    def __init__(self, verb):
        super().__init__()
        self.verb = verb

    def run(self):
        ok, out = run(self.verb, timeout=60)
        self.done.emit(ok, out)


def hexagon(cx, cy, r):
    poly = QPolygonF()
    for i in range(6):
        a = math.radians(60 * i - 90)
        poly.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
    return poly


class Shield(QWidget):
    """Hexagonal shield with a round power button."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(260, 290)
        self.state = "off"       # off | on | busy
        self.setCursor(Qt.PointingHandCursor)

    def set_state(self, state):
        self.state = state
        self.update()

    def mousePressEvent(self, ev):
        cx, cy = self.width() / 2, self.height() / 2
        r = min(self.width(), self.height()) * 0.22
        if (ev.position().x() - cx) ** 2 + (ev.position().y() - cy) ** 2 <= r * r:
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        rs = min(w, h) * 0.46

        # soft glow
        glow = QRadialGradient(QPointF(cx, cy), rs * 1.5)
        base = QColor(GREEN if self.state == "on" else GREY)
        glow.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 60))
        glow.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), rs * 1.5, rs * 1.5)

        # hexagon
        grad = QLinearGradient(cx, cy - rs, cx, cy + rs)
        if self.state == "on":
            grad.setColorAt(0, QColor(GREEN_LIGHT))
            grad.setColorAt(1, QColor(GREEN))
        else:
            grad.setColorAt(0, QColor("#9aa0a6"))
            grad.setColorAt(1, QColor("#6b7075"))
        p.setBrush(grad)
        p.drawPolygon(hexagon(cx, cy, rs))

        # round button
        rb = rs * 0.48
        btn = QRadialGradient(QPointF(cx, cy - rb * 0.3), rb * 1.6)
        btn.setColorAt(0, QColor("#ffffff"))
        btn.setColorAt(1, QColor("#dfe1e5"))
        p.setBrush(btn)
        p.setPen(QPen(QColor(0, 0, 0, 25), 1))
        p.drawEllipse(QPointF(cx, cy), rb, rb)

        # power glyph
        col = QColor(GREEN if self.state == "on" else "#7b8085")
        if self.state == "busy":
            col = QColor(AMBER)
        pen = QPen(col, max(3.0, rb * 0.12), Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rr = rb * 0.52
        path = QPainterPath()
        path.arcMoveTo(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), 115)
        path.arcTo(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), 115, 310)
        p.drawPath(path)
        p.drawLine(QPointF(cx, cy - rr * 1.25), QPointF(cx, cy - rr * 0.15))
        p.end()


class SideButton(QPushButton):
    def __init__(self, glyph, label):
        super().__init__()
        self.setCheckable(True)
        self.setFixedHeight(62)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(f"{glyph}\n{label}")
        self.setStyleSheet(f"""
            QPushButton {{
                border: none; color: {SIDEBAR_FG};
                background: transparent; font-size: 10px;
            }}
            QPushButton:checked {{ color: {SIDEBAR_ACTIVE}; background: #2f2f3c; }}
            QPushButton:hover {{ background: #2a2a36; }}
        """)


class Home(QWidget):
    def __init__(self, shield):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 22, 16, 22)

        self.status = QLabel("—")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("", 22, QFont.Bold))

        self.timer = QLabel("")
        self.timer.setAlignment(Qt.AlignCenter)
        self.timer.setFont(QFont("", 10, QFont.Bold))
        self.timer.setStyleSheet(f"color:{DARK};")

        self.name = QLabel("")
        self.name.setAlignment(Qt.AlignCenter)
        self.name.setFont(QFont("", 15))
        self.name.setStyleSheet(f"color:{DARK};")

        self.account = QLabel("")
        self.account.setAlignment(Qt.AlignCenter)
        self.account.setStyleSheet(f"color:{GREY};")

        self.pop = QLabel("")
        self.pop.setAlignment(Qt.AlignCenter)
        self.pop.setStyleSheet(f"color:{GREY};")

        lay.addWidget(self.status)
        lay.addWidget(self.timer)
        lay.addStretch(1)
        lay.addWidget(shield, alignment=Qt.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(self.name)
        lay.addWidget(self.account)
        lay.addWidget(self.pop)


class RawPage(QWidget):
    def __init__(self, title):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 18, 16, 18)
        h = QLabel(title)
        h.setFont(QFont("", 14, QFont.Bold))
        h.setStyleSheet(f"color:{DARK};")
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setStyleSheet(
            "QTextEdit{background:#ffffff;border:1px solid #dcdce2;border-radius:6px;}")
        lay.addWidget(h)
        lay.addWidget(self.body)


def make_icon(connected):
    """Tray icon: small hexagon with a white dot, green when connected, grey otherwise."""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = size / 2
    g = QLinearGradient(c, 2, c, size - 2)
    if connected:
        g.setColorAt(0, QColor(GREEN_LIGHT))
        g.setColorAt(1, QColor(GREEN))
    else:
        g.setColorAt(0, QColor("#9aa0a6"))
        g.setColorAt(1, QColor("#6b7075"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPolygon(hexagon(c, c, size * 0.46))
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(c, c), size * 0.15, size * 0.15)
    p.end()
    return QIcon(pm)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(392, 572)
        self.busy = False
        self.seconds = 0
        self.status = Status()

        self.shield = Shield()
        self.shield.clicked.connect(self.toggle)

        self.home = Home(self.shield)
        self.stats = RawPage("Stats")
        self.settings = RawPage("Settings")
        self.about = RawPage("About")

        self.pages = QStackedWidget()
        for w in (self.home, self.stats, self.settings, self.about):
            self.pages.addWidget(w)
        self.pages.setStyleSheet(f"background:{PAGE_BG};")

        bar = QFrame()
        bar.setFixedWidth(68)
        bar.setStyleSheet(f"background:{SIDEBAR_BG};")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(0, 10, 0, 10)
        bl.setSpacing(2)
        self.buttons = []
        for i, (g, t) in enumerate((("✔", "Home"), ("▌█", "Stats"),
                                    ("⚙", "Settings"), ("ℹ", "About"))):
            b = SideButton(g, t)
            b.clicked.connect(lambda _=False, n=i: self.go(n))
            bl.addWidget(b)
            self.buttons.append(b)
        bl.addStretch(1)
        self.buttons[0].setChecked(True)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(bar)
        rl.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self.tray = QSystemTrayIcon(make_icon(False), self)
        menu = QMenu()
        self.act_toggle = QAction("Connect", self)
        self.act_toggle.triggered.connect(self.toggle)
        act_show = QAction("Show window", self)
        act_show.triggered.connect(self.showNormal)
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(self.act_toggle)
        menu.addSeparator()
        menu.addAction(act_show)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.showNormal() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        QTimer.singleShot(0, self.tray.show)      # register again once the event loop runs
        QTimer.singleShot(2500, self.tray.show)   # and once more, in case the panel was slow

        _, ver = run("version")
        self.about.body.setPlainText(
            f"{APP_NAME} {__version__}\n"
            "Unofficial front-end, not affiliated with Cato Networks.\n"
            "License: MIT\n\n"
            f"Client version reported by {CMD}:\n{ver or '—'}")

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(4000)

        self.tick = QTimer(self)
        self.tick.timeout.connect(self.bump)
        self.tick.start(1000)

        self.refresh()

    def go(self, n):
        for i, b in enumerate(self.buttons):
            b.setChecked(i == n)
        self.pages.setCurrentIndex(n)

    def bump(self):
        if self.status.connected and not self.status.uptime:
            self.seconds += 1
            h, rem = divmod(self.seconds, 3600)
            m, s = divmod(rem, 60)
            self.home.timer.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def refresh(self):
        # If the panel restarts, the registered tray icon is lost: show it again.
        if not self.tray.isVisible():
            self.tray.show()
        # NEVER replace a thread that is still running: Qt would abort the process.
        p = getattr(self, "_p", None)
        if p is not None and p.isRunning():
            return
        self._p = Poller()
        self._p.got.connect(self.apply)
        self._p.start()

    def apply(self, st: Status):
        was = self.status.connected
        self.status = st
        if st.connected and not was:
            self.seconds = 0

        connecting = self.busy or st.connecting
        self.home.status.setText("Connecting…" if connecting else st.text)
        self.home.status.setStyleSheet(f"color:{AMBER if connecting else st.color};")
        if st.uptime:
            self.home.timer.setText(st.uptime)
        elif not st.connected:
            self.home.timer.setText("")
        self.home.name.setText(st.name)
        self.home.account.setText(st.account)
        self.home.pop.setText(st.pop)

        self.shield.set_state("busy" if connecting else ("on" if st.connected else "off"))
        self.tray.setIcon(make_icon(st.connected))
        self.tray.setToolTip(f"{APP_NAME} — {st.text}")
        self.act_toggle.setText("Disconnect" if st.connected else "Connect")

        self.stats.body.setPlainText(st.raw or "—")
        if not st.daemon_ok:
            self.settings.body.setPlainText(
                "The client daemon is not responding.\n\n"
                "Check that the Cato client service is enabled and running,\n"
                "and that your user may talk to it. Service and group names\n"
                "depend on how the client was installed, for example:\n\n"
                "  sudo systemctl enable --now cato-client.service\n"
                "  sudo usermod -aG cato-client $USER   (then log out and in)\n\n"
                f"Raw output:\n{st.raw}")
        else:
            self.settings.body.setPlainText(
                f"The client is configured with the {CMD} command.\n\n"
                f"  {CMD} start --help   connection options\n"
                f"  {CMD} import-cert    import a device certificate\n"
                f"  {CMD} update         update the client\n")

    def toggle(self):
        if self.busy:
            return
        a = getattr(self, "_a", None)
        if a is not None and a.isRunning():
            return
        self.busy = True
        self.shield.set_state("busy")
        self.home.status.setText("Connecting…")
        verb = "stop" if self.status.connected else "start"
        self._a = Action(verb)
        self._a.done.connect(self.finished)
        self._a.start()

    def finished(self, ok, out):
        self.busy = False
        if not ok and out:
            self.stats.body.setPlainText(out)
        self.refresh()

    def closeEvent(self, ev):
        # Closing the window keeps the app in the tray. Quit from the tray menu.
        ev.ignore()
        if self.tray.isVisible() or QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()
        if not getattr(self, "_warned", False):
            self._warned = True
            self.tray.showMessage(APP_NAME,
                                  "The application keeps running in the system tray.",
                                  QSystemTrayIcon.Information, 4000)


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    path = os.path.join(base, APP_ID)
    os.makedirs(path, exist_ok=True)
    return path


def main():
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {__version__}")
        return

    crash = open(os.path.join(state_dir(), "crash.log"), "a")
    faulthandler.enable(crash)                      # abort or segfault: trace to file

    def hook(t, v, tb):
        crash.write("".join(traceback.format_exception(t, v, tb)))
        crash.flush()
    sys.excepthook = hook                           # Python exceptions: log, do not exit

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)                  # Wayland app_id matches the .desktop file
    app.setWindowIcon(QIcon.fromTheme(APP_ID, make_icon(False)))
    app.setQuitOnLastWindowClosed(False)

    # Single instance: if the GUI is already open, bring it to the front and exit.
    sock = f"{APP_ID}-single-instance"
    probe = QLocalSocket()
    probe.connectToServer(sock)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        sys.exit(0)
    QLocalServer.removeServer(sock)                 # stale socket left by a crash
    server = QLocalServer()
    server.listen(sock)

    w = Window()

    def on_second_instance():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.deleteLater()
        w.showNormal()
        w.raise_()
        w.activateWindow()
    server.newConnection.connect(on_second_instance)

    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
