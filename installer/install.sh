#!/usr/bin/env bash
# AutoTranscript - Installateur Linux
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/.venv"

echo ""
echo "======================================"
echo "  AutoTranscript - Installation"
echo "======================================"
echo ""

# --- 1. Verifier Python ---
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version)
    echo "[OK] Python detecte : $PY_VER"
    PYTHON=python3
else
    echo "[!] python3 est requis. Installez-le avec votre gestionnaire de paquets :"
    echo "    Debian/Ubuntu : sudo apt install python3 python3-pip python3-venv"
    echo "    Fedora        : sudo dnf install python3"
    echo "    Arch          : sudo pacman -S python"
    exit 1
fi

# Sur Debian/Ubuntu, s'assurer que python3-venv, python3-pip et python3-tk sont presents
if command -v apt-get &>/dev/null; then
    MISSING=""
    $PYTHON -m venv --help &>/dev/null || MISSING="$MISSING python3-venv"
    $PYTHON -m pip --version &>/dev/null || MISSING="$MISSING python3-pip"
    $PYTHON -c "import tkinter" &>/dev/null || MISSING="$MISSING python3-tk"
    if [ -n "$MISSING" ]; then
        echo "[...] Installation des paquets systeme manquants :$MISSING"
        sudo apt-get install -y $MISSING
    fi
fi

# --- 2. Verifier / installer ffmpeg ---
if command -v ffmpeg &>/dev/null; then
    echo "[OK] ffmpeg detecte."
else
    echo "[...] ffmpeg non trouve. Tentative d'installation..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y ffmpeg
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y ffmpeg
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm ffmpeg
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y ffmpeg
    else
        echo "[!] Impossible d'installer ffmpeg automatiquement."
        echo "    Installez-le manuellement puis relancez ce script."
        exit 1
    fi
    echo "[OK] ffmpeg installe."
fi

# --- 3. Creer le venv ---
if [ ! -d "$VENV_DIR" ]; then
    echo "[...] Creation de l'environnement virtuel..."
    $PYTHON -m venv "$VENV_DIR"
    echo "[OK] Environnement virtuel cree."
else
    echo "[OK] Environnement virtuel existant detecte."
fi

PYTHON_VENV="$VENV_DIR/bin/python"

# Bootstrap pip dans le venv si absent
if [ ! -f "$VENV_DIR/bin/pip" ]; then
    echo "[...] pip absent du venv, bootstrap en cours..."
    "$PYTHON_VENV" -m ensurepip --upgrade 2>/dev/null || \
        curl -sSL https://bootstrap.pypa.io/get-pip.py | "$PYTHON_VENV"
fi

# --- 4. Installer les dependances ---
echo "[...] Installation des dependances (peut prendre plusieurs minutes)..."
"$PYTHON_VENV" -m pip install --upgrade pip --quiet
"$PYTHON_VENV" -m pip install -r "$APP_DIR/requirements.txt" --quiet
echo "[OK] Dependances installees."

# --- 5. Creer le lanceur ---
LAUNCHER="$APP_DIR/lancer.sh"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
"$PYTHON_VENV" "$APP_DIR/app/main.py"
EOF
chmod +x "$LAUNCHER"
echo "[OK] Lanceur cree : $LAUNCHER"

# --- 6. Entree menu applications (optionnel) ---
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/autotranscript.desktop"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AutoTranscript
Comment=Transcription audio avec Whisper AI
Exec=$LAUNCHER
Terminal=false
Categories=Utility;AudioVideo;
EOF
echo "[OK] Entree menu applications creee."

echo ""
echo "======================================"
echo "  Installation terminee !"
echo "  Lancez l'application avec :"
echo "    ./lancer.sh"
echo "  Ou depuis le menu applications."
echo "======================================"
echo ""
