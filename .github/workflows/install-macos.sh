#!/bin/bash

set -x

uv run python -c 'import sys; print(sys.version)'

# For macOS Big Sur, the stable portaudio (19.6.0) makes friture-monitor freeze on startup
# install from a newer master commit instead
# see: https://github.com/tlecomte/friture/issues/154
PORTAUDIO_COMMIT=aa7a7902f1b79502633aeb88919657af46c84193
rm -rf build/portaudio
git clone https://github.com/PortAudio/portaudio.git build/portaudio
cd build/portaudio
git checkout $PORTAUDIO_COMMIT
./configure --enable-mac-universal=no --enable-cxx
make
sudo make install
cd -

uv run pyinstaller friture-monitor.spec -y

ls -la dist/*

# compare the portaudio libs to make sure the package contains the one that was installed with brew
ls -la /usr/local/lib/libportaudio.dylib
ls -la dist/friture-monitor.app/Contents/Frameworks/_sounddevice_data/portaudio-binaries

# PyInstaller will try to codesign friture-monitor.app, but will fail because of the Qt5 file structure
# (this is visible in the logs)
# see https://github.com/pyinstaller/pyinstaller/wiki/Recipe-OSX-Code-Signing-Qt
# so we fix the folder names and then sign again manually
uv run python installer/fix_app_qt_folder_names_for_codesign.py dist/friture-monitor.app
codesign -s - --force --all-architectures --timestamp --deep dist/friture-monitor.app
codesign -dv dist/friture-monitor.app

# prepare a dmg out of friture-monitor.app
export ARTIFACT_FILENAME=friture-monitor-$(uv run python -c 'import friture_monitor; print(friture_monitor.__version__)')-$(date +'%Y%m%d').dmg
echo $ARTIFACT_FILENAME

# sanity check: a healthy friture-monitor .app bundle is well under 200 MB.
# A much larger result usually means a packaging step duplicated the Qt/Python
# libs, so fail loudly rather than ship a bloated artifact.
APP_BUNDLE_SIZE_BYTES=$(du -sk dist/friture-monitor.app | awk '{print $1}')
echo "friture-monitor.app size: $APP_BUNDLE_SIZE_BYTES KB"
if [ "$APP_BUNDLE_SIZE_BYTES" -gt 200000 ]; then
    echo "ERROR: friture-monitor.app is unexpectedly large (>200MB); aborting."
    exit 1
fi

# Build the DMG with a polished layout (icon positioning + a drop zone for
# /Applications) using create-dmg.
brew install create-dmg

create-dmg \
    --volname "friture-monitor" \
    --window-pos 200 122 \
    --window-size 600 400 \
    --icon-size 100 \
    --hide-extension "friture-monitor.app" \
    --icon "friture-monitor.app" 150 190 \
    --app-drop-link 450 190 \
    --background "installer/dmg-background.png" \
    --hdiutil-retries 30 \
    --no-internet-enable \
    "$ARTIFACT_FILENAME" \
    dist/friture-monitor.app

du -hs dist/friture-monitor.app
du -hs "$ARTIFACT_FILENAME"
