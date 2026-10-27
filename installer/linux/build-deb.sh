#!/usr/bin/env bash
# Construit un paquet .deb pour AutoTranscript
# Usage : VERSION=2.2.0 ./build-deb.sh
set -e

VERSION="${VERSION:-2.2.0}"
PACKAGE="autotranscript"
ARCH="all"
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="$APP_DIR/dist/deb-build"
PKG_ROOT="$BUILD_DIR/${PACKAGE}_${VERSION}_${ARCH}"

echo "[...] Construction du paquet ${PACKAGE}_${VERSION}_${ARCH}.deb"

rm -rf "$PKG_ROOT"
mkdir -p \
  "$PKG_ROOT/DEBIAN" \
  "$PKG_ROOT/opt/autotranscript/app" \
  "$PKG_ROOT/opt/autotranscript/i18n" \
  "$PKG_ROOT/usr/local/bin" \
  "$PKG_ROOT/usr/share/applications"

# --- Fichiers de l'application ---
cp -r "$APP_DIR/app/."    "$PKG_ROOT/opt/autotranscript/app/"
cp -r "$APP_DIR/i18n/."   "$PKG_ROOT/opt/autotranscript/i18n/"
cp    "$APP_DIR/models.json"      "$PKG_ROOT/opt/autotranscript/"
cp    "$APP_DIR/requirements.txt" "$PKG_ROOT/opt/autotranscript/"

# --- DEBIAN/control ---
cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Architecture: $ARCH
Maintainer: Nicolas Mallent <nicolas.mallent@magellium.fr>
Depends: python3-venv, python3-tk, ffmpeg
Section: utils
Priority: optional
Homepage: https://github.com/NicolasMallent/autoTranscript
Description: Transcription automatique audio/video avec Whisper AI
 Application de bureau pour transcrire des fichiers audio et video
 en texte horodate, en utilisant Whisper AI d'OpenAI.
 Traitement entierement local, conforme au RGPD.
EOF

# --- DEBIAN/postinst : installe les dependances Python apres installation ---
cat > "$PKG_ROOT/DEBIAN/postinst" <<'POSTINST'
#!/bin/bash
set -e
INSTALL_DIR=/opt/autotranscript
VENV_DIR=$INSTALL_DIR/.venv
REQUIREMENTS=$INSTALL_DIR/requirements.txt
LOG_FILE=$INSTALL_DIR/install.log

echo "AutoTranscript : creation de l'environnement Python..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet

echo "AutoTranscript : installation des dependances IA..."
echo "(telechargement de ~3 Go, cela peut prendre plusieurs minutes)"
echo "Journal d'installation : $LOG_FILE"
: > "$LOG_FILE"

# Versions epinglees dans requirements.txt (whisperx, pyannote.audio, customtkinter...) : ce sont
# celles qui sont testees. Si l'installation echoue (ex. Python 3.14+, whisperx incompatible),
# repli sur openai-whisper (transcription seule, sans identification des locuteurs).
if "$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS" >> "$LOG_FILE" 2>&1; then
    echo "AutoTranscript : dependances installees (toutes les fonctionnalites disponibles)."
    # Donnees de decoupage en phrases (alignement des mots) : installees par root dans le venv.
    # NLTK n'accepte que des dossiers prives (proprietaire root ou l'utilisateur, non modifiables par
    # les autres) : celui-ci l'est, il est lisible par tous et fonctionne hors ligne. Un echec
    # n'interrompt pas l'installation : l'application les retelechargera au premier usage.
    if "$VENV_DIR/bin/python" -m nltk.downloader -d "$VENV_DIR/nltk_data" punkt_tab >> "$LOG_FILE" 2>&1; then
        echo "AutoTranscript : donnees de decoupage en phrases installees."
    else
        echo "AutoTranscript : donnees de decoupage en phrases non installees (voir $LOG_FILE) : telechargement au premier usage."
    fi
else
    echo "AutoTranscript : echec de l'installation complete (details dans $LOG_FILE)."
    echo "  Installation de openai-whisper (transcription sans identification des locuteurs)."
    CUSTOMTKINTER="$(grep -i '^customtkinter' "$REQUIREMENTS")"
    "$VENV_DIR/bin/python" -m pip install openai-whisper "$CUSTOMTKINTER" >> "$LOG_FILE" 2>&1
fi

echo "AutoTranscript : installation terminee."
POSTINST
chmod 755 "$PKG_ROOT/DEBIAN/postinst"

# --- DEBIAN/prerm : nettoie le venv avant desinstallation ---
cat > "$PKG_ROOT/DEBIAN/prerm" <<'PRERM'
#!/bin/bash
set -e
rm -rf /opt/autotranscript/.venv
rm -f /opt/autotranscript/install.log
PRERM
chmod 755 "$PKG_ROOT/DEBIAN/prerm"

# --- Lanceur systeme ---
cat > "$PKG_ROOT/usr/local/bin/autotranscript" <<'LAUNCHER'
#!/bin/bash
exec /opt/autotranscript/.venv/bin/python /opt/autotranscript/app/main.py "$@"
LAUNCHER
chmod 755 "$PKG_ROOT/usr/local/bin/autotranscript"

# --- Entree menu applications ---
cat > "$PKG_ROOT/usr/share/applications/autotranscript.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AutoTranscript
Comment=Transcription audio avec Whisper AI
Exec=autotranscript
Terminal=false
Categories=Utility;AudioVideo;
EOF

# --- Construction du .deb ---
mkdir -p "$APP_DIR/dist"
dpkg-deb --build --root-owner-group "$PKG_ROOT" \
  "$APP_DIR/dist/${PACKAGE}_${VERSION}_${ARCH}.deb"

echo "[OK] Paquet cree : dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
