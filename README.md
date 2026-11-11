# SDP Shield

An unofficial graphical front-end for the **Cato Networks Linux client**.

The Linux client is driven from the command line with `cato-sdp`. SDP Shield
adds a small window and a system tray icon so you can see whether you are
connected and connect or disconnect with one click.

> **Disclaimer.** SDP Shield is an independent, community project. It is not
> affiliated with, endorsed by, or supported by Cato Networks. "Cato" and
> "Cato Networks" are trademarks of their respective owner and are used here
> only to say which client this tool works with.

## What it does

- Shows the connection state: connected, connecting, disconnected, or daemon not running.
- Connects and disconnects with the big button or from the tray menu.
- Shows the connection time, PoP and tunnel IP when the client reports them.
- Shows the raw `cato-sdp status` output on the Stats page.
- Keeps running in the system tray when you close the window.
- Runs as a single instance: starting it again brings the window to the front.

## What it does not do

- It does **not** include, bundle or redistribute any Cato software.
- It does **not** read, store or send credentials, certificates or configuration.
- It opens **no** network connections. It only runs these local commands:
  `cato-sdp status`, `cato-sdp start`, `cato-sdp stop`, `cato-sdp version`.
- It does not run anything with root privileges.

## Requirements

- Linux with a desktop that supports a system tray (KDE Plasma, GNOME with the
  AppIndicator extension, Xfce, and others). Works on Wayland and X11.
- Python 3.9 or newer.
- PySide6 (Qt for Python).
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
sudo apt install git python3-pyside6.qtwidgets python3-pyside6.qtnetwork
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

- Click the round button in the middle to connect or disconnect.
- Right-click the tray icon for Connect, Show window and Quit.
- Closing the window keeps the app in the tray. Use **Quit** to exit.

To start it automatically at login, add it to your desktop's autostart settings.

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

## Development

```bash
python3 -m unittest discover tests
```

The whole application is one file, `sdp_shield.py`.

## License

MIT, see [LICENSE](LICENSE).

SDP Shield uses PySide6, which is available under the LGPLv3. It is used as
an unmodified, dynamically loaded library installed separately by the user.
