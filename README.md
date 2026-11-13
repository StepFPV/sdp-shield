# SDP Shield

An unofficial graphical front-end for the **Cato Networks Linux client**.

The Linux client is driven from the command line with `cato-sdp`. SDP Shield
adds a dark, compact window and a system tray icon so you can see whether you
are connected, connect or disconnect with one click, and check the details of
the session.

> **Disclaimer.** SDP Shield is an independent, community project. It is not
> affiliated with, endorsed by, or supported by Cato Networks. "Cato" and
> "Cato Networks" are trademarks of their respective owner and are used here
> only to say which client this tool works with.

## What it does

- **Home**: connection state (connected, connecting, disconnected, daemon not
  running) with a live timer, a shield button to connect or disconnect, and the
  user, account and PoP reported by the client.
- **Statistics**: data sent and received, packets, local and tunnel IP, PoP and
  its address, latency, session start, DNS servers and the client version.
- **Users**: keep a list of user/account pairs and pick the one to connect
  with, optionally with a custom PoP server address. The user reported by the
  client is added automatically. Editing is locked while connected.
- **Settings**: start at login, connect when the app starts, Always-On
  (reconnect when the tunnel drops on its own), and the `cato-sdp start`
  options for systemd-resolved DNS, TCP-only transport and a split-tunnel
  route. Connection options can be changed only while disconnected.
  Desktop notifications can be switched on or off.
- **Support**: record the client log while you reproduce an issue, or save all
  client logs and the current status to a `.tar.gz` for your IT department.
- **Feedback**: rate the experience and write a note. It is saved locally and
  copied to the clipboard; it is not sent anywhere.
- Frameless window with a collapsible sidebar, system tray icon, single
  instance (starting it again brings the window to the front).

## What it does not do

- It does **not** include, bundle or redistribute any Cato software.
- It does **not** read, store or send credentials or certificates. The log
  archive never includes the client's credential files.
- It does not contact any server of its own. It only runs these local
  commands: `cato-sdp status`, `cato-sdp start` (with the options you chose),
  `cato-sdp stop`, `cato-sdp version` and, for the log archive,
  `journalctl -u cato-client`.
- It does not run anything with root privileges.

## Files

- `~/.config/sdp-shield/settings.json` and `users.json`: your settings and the
  user/account list (no passwords).
- `~/.config/autostart/sdp-shield.desktop`: only when "Start at login" is on.
- `~/.local/state/sdp-shield/`: crash log and saved feedback.

## Requirements

- Linux with a desktop that supports a system tray (KDE Plasma, GNOME with the
  AppIndicator extension, Xfce, and others). Works on Wayland and X11.
- Python 3.9 or newer.
- PySide6 (Qt for Python), including the QtSvg module.
- The Cato Networks Linux client, installed and set up as provided by your
  network administrator. SDP Shield expects the `cato-sdp` command in `PATH`.

Tested with client version 5.8.1 on Arch Linux with KDE Plasma 6.
The `cato-sdp` output format may change in future client versions.

## Installation

### Arch Linux and derivatives

```bash
sudo pacman -S --needed python pyside6
git clone https://github.com/StepFPV/sdp-shield.git sdp-shield
cd sdp-shield/packaging/arch
makepkg -si
```

### Debian, Ubuntu and derivatives

Tested on Debian 13 and Ubuntu 26.04 LTS, which package PySide6.

```bash
sudo apt install git python3-pyside6.qtwidgets python3-pyside6.qtnetwork python3-pyside6.qtsvg
git clone https://github.com/StepFPV/sdp-shield.git sdp-shield
cd sdp-shield
packaging/debian/build-deb.sh
sudo apt install ./sdp-shield_*_all.deb
```

### Any distribution, current user only

Install PySide6 with your package manager, then:

```bash
git clone https://github.com/StepFPV/sdp-shield.git sdp-shield
cd sdp-shield
./install.sh
```

This installs into `~/.local` and needs no root. Remove it with `./uninstall.sh`.

### Ubuntu 24.04 and older

These releases do not package PySide6. Install it in a virtual environment
and point the installer at it:

```bash
sudo apt install git python3-venv
python3 -m venv ~/.local/share/sdp-shield-venv
~/.local/share/sdp-shield-venv/bin/pip install PySide6
git clone https://github.com/StepFPV/sdp-shield.git sdp-shield
cd sdp-shield
PYTHON=~/.local/share/sdp-shield-venv/bin/python ./install.sh
```

## Usage

Start **SDP Shield** from the application menu, or run `sdp-shield`.

- Click the round button in the shield to connect or disconnect.
- Right-click the tray icon for Connect, Show window and Quit.
- The red dot hides the window to the tray, the yellow one minimises it.
  Drag the window from any empty area. Use **Quit** in the tray menu to exit.
- To start it automatically at login, tick **Start at login** in Settings.
  `sdp-shield --hidden` starts it in the tray without opening the window.

## Troubleshooting

**"Daemon not running".** The Cato client service is not running or your
user is not allowed to talk to it. Service and group names depend on how the
client was installed. With a typical installation:

```bash
sudo systemctl enable --now cato-client.service
sudo usermod -aG cato-client "$USER"
```

Log out and back in after changing groups.

**"cato-sdp was not found".** The Cato client is not installed or not in `PATH`.

**No tray icon on GNOME.** Install and enable the AppIndicator extension.

**Crash log.** Errors are written to `~/.local/state/sdp-shield/crash.log`.

**Switching user.** When you pick a different user, SDP Shield passes
`--user` and `--account` to `cato-sdp start`; the client then asks you to sign
in for that user.

## Development

```bash
python3 -m unittest discover tests
```

The whole application is one file, `sdp_shield.py`.

## License

MIT, see [LICENSE](LICENSE).

SDP Shield uses PySide6, which is available under the LGPLv3. It is used as
an unmodified, dynamically loaded library installed separately by the user.
