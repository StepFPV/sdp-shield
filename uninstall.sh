#!/bin/sh
# Remove a user installation made with install.sh.
set -eu
PREFIX="${PREFIX:-$HOME/.local}"
rm -f  "$PREFIX/bin/sdp-shield" \
       "$PREFIX/share/applications/sdp-shield.desktop" \
       "$PREFIX/share/icons/hicolor/scalable/apps/sdp-shield.svg"
rm -rf "$PREFIX/share/sdp-shield"
echo "Removed. Logs in ${XDG_STATE_HOME:-$HOME/.local/state}/sdp-shield can be deleted by hand."
