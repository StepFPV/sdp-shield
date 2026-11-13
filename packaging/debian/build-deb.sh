#!/bin/sh
# Builds sdp-shield_<version>_all.deb from this source tree. Needs dpkg-deb.
# Usage: packaging/debian/build-deb.sh   then   sudo apt install ./sdp-shield_*.deb
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/sdp_shield.py")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PKG="$WORK/sdp-shield"

install -Dm755 "$ROOT/sdp_shield.py"      "$PKG/usr/share/sdp-shield/sdp_shield.py"
install -Dm644 "$ROOT/sdp-shield.desktop" "$PKG/usr/share/applications/sdp-shield.desktop"
install -Dm644 "$ROOT/sdp-shield.svg"     "$PKG/usr/share/icons/hicolor/scalable/apps/sdp-shield.svg"
install -Dm644 "$ROOT/LICENSE"            "$PKG/usr/share/doc/sdp-shield/copyright"
install -dm755 "$PKG/usr/bin" "$PKG/DEBIAN"
printf '#!/bin/sh\nexec python3 /usr/share/sdp-shield/sdp_shield.py "$@"\n' > "$PKG/usr/bin/sdp-shield"
chmod 755 "$PKG/usr/bin/sdp-shield"

cat > "$PKG/DEBIAN/control" <<CTRL
Package: sdp-shield
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Depends: python3, python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets, python3-pyside6.qtnetwork, python3-pyside6.qtsvg
Suggests: cato-client
Maintainer: sdp-shield contributors <nobody@invalid>
Description: Unofficial graphical front-end for the Cato Networks Linux client
 Shows the connection state of the Cato client and lets you connect and
 disconnect from a window or the system tray. It only runs the cato-sdp
 command. Not affiliated with Cato Networks.
CTRL

dpkg-deb --root-owner-group --build "$PKG" "$ROOT/sdp-shield_${VERSION}_all.deb"
echo "Built: $ROOT/sdp-shield_${VERSION}_all.deb"
