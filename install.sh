#!/bin/sh
# Install SDP Shield for the current user (no root needed).
# Usage: ./install.sh            installs into ~/.local
#        PREFIX=/some/dir ./install.sh
#        PYTHON=/path/to/venv/bin/python ./install.sh   use PySide6 from a virtualenv
set -eu
cd "$(dirname "$0")"
PREFIX="${PREFIX:-$HOME/.local}"
PYTHON="$(command -v "${PYTHON:-python3}")" || { echo "Python 3 not found." >&2; exit 1; }

"$PYTHON" -c 'import PySide6' 2>/dev/null || {
    echo "PySide6 is missing. Install it first:" >&2
    echo "  Arch:          sudo pacman -S pyside6" >&2
    echo "  Debian/Ubuntu: sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtnetwork" >&2
    echo "  Or use a virtualenv: see 'Ubuntu 24.04 and older' in README.md" >&2
    exit 1
}
command -v cato-sdp >/dev/null 2>&1 || \
    echo "Warning: cato-sdp not found. Install the Cato client from your administrator first." >&2

install -Dm755 sdp_shield.py      "$PREFIX/share/sdp-shield/sdp_shield.py"
install -Dm644 sdp-shield.desktop "$PREFIX/share/applications/sdp-shield.desktop"
install -Dm644 sdp-shield.svg     "$PREFIX/share/icons/hicolor/scalable/apps/sdp-shield.svg"
mkdir -p "$PREFIX/bin"
cat > "$PREFIX/bin/sdp-shield" <<LAUNCH
#!/bin/sh
exec "$PYTHON" "$PREFIX/share/sdp-shield/sdp_shield.py" "\$@"
LAUNCH
chmod 755 "$PREFIX/bin/sdp-shield"

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo "Installed. Start it from the application menu or run: sdp-shield"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Note: $PREFIX/bin is not in your PATH." ;; esac
