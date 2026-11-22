#!/bin/bash
# Build Lanternfish.app against this checkout's .venv and install it in /Applications.
# Python code runs from the checkout, so only launcher changes need a rebuild.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python="$root/.venv/bin/python"
config="$("$python" -c 'import sys; print(f"{sys.base_prefix}/bin/python{sys.version_info[0]}.{sys.version_info[1]}-config")')"
app="/Applications/Lanternfish.app"

mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$root/macos/Info.plist" "$app/Contents/Info.plist"
if [ -f "$root/macos/AppIcon.icns" ]; then
    cp "$root/macos/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
fi
# shellcheck disable=SC2046  # The config flags must split into separate arguments.
clang -O2 -DVENV_PYTHON="\"$python\"" "$root/macos/launcher.c" \
    $("$config" --includes) $("$config" --embed --ldflags) \
    -o "$app/Contents/MacOS/Lanternfish"
codesign --force --sign - --identifier com.yuxuanyan.lanternfish "$app"

echo "Installed $app"
