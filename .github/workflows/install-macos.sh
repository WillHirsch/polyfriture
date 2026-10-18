#!/bin/bash

set -x

uv run python -c 'import sys; print(sys.version)'

# For macOS Big Sur, the stable portaudio (19.6.0) makes polyfriture freeze on startup
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

uv run pyinstaller polyfriture.spec -y

ls -la dist/*

# compare the portaudio libs to make sure the package contains the one that was installed with brew
ls -la /usr/local/lib/libportaudio.dylib
ls -la dist/polyfriture.app/Contents/Frameworks/_sounddevice_data/portaudio-binaries

# PyInstaller will try to codesign polyfriture.app, but will fail because of the Qt5 file structure
# (this is visible in the logs)
# see https://github.com/pyinstaller/pyinstaller/wiki/Recipe-OSX-Code-Signing-Qt
# so we fix the folder names and then sign again manually
uv run python installer/fix_app_qt_folder_names_for_codesign.py dist/polyfriture.app
codesign -s - --force --all-architectures --timestamp --deep dist/polyfriture.app
codesign -dv dist/polyfriture.app

# prepare a dmg out of polyfriture.app
export ARTIFACT_FILENAME=polyfriture-$(uv run python -c 'import polyfriture; print(polyfriture.__version__)')-$(date +'%Y%m%d').dmg
echo $ARTIFACT_FILENAME

# sanity check: a healthy polyfriture .app bundle is well under 200 MB.
# A much larger result usually means a packaging step duplicated the Qt/Python
# libs, so fail loudly rather than ship a bloated artifact.
APP_BUNDLE_SIZE_BYTES=$(du -sk dist/polyfriture.app | awk '{print $1}')
echo "polyfriture.app size: $APP_BUNDLE_SIZE_BYTES KB"
if [ "$APP_BUNDLE_SIZE_BYTES" -gt 200000 ]; then
    echo "ERROR: polyfriture.app is unexpectedly large (>200MB); aborting."
    exit 1
fi

# Build the DMG with a polished layout (icon positioning + a drop zone for
# /Applications) using create-dmg.
brew install create-dmg

create-dmg \
    --volname "Polyfriture" \
    --window-pos 200 122 \
    --window-size 600 400 \
    --icon-size 100 \
    --hide-extension "polyfriture.app" \
    --icon "polyfriture.app" 150 190 \
    --app-drop-link 450 190 \
    --background "installer/dmg-background.png" \
    --hdiutil-retries 30 \
    --no-internet-enable \
    "$ARTIFACT_FILENAME" \
    dist/polyfriture.app

du -hs dist/polyfriture.app
du -hs "$ARTIFACT_FILENAME"
