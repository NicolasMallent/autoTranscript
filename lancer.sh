#!/usr/bin/env bash
# Lance AutoTranscript depuis l'environnement virtuel créé par installer/install.sh.
# Les chemins sont relatifs à ce fichier : le dépôt peut être déplacé ou cloné n'importe où.
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PYTHON="$DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Environnement virtuel introuvable ($DIR/.venv). Lancez d'abord : installer/install.sh" >&2
    exit 1
fi

exec "$PYTHON" "$DIR/app/main.py" "$@"
