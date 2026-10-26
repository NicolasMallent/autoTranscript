"""
Test lent, avec le vrai modèle pyannote : la pipeline doit se charger hors ligne et sans token.

Ignoré par défaut. Pour le lancer, pointer vers le dossier du modèle (celui que produit
scripts/download_pyannote.py, ou ~/.autotranscript/models/speaker-diarization-community-1) :

    AUTOTRANSCRIPT_MODEL_DIR=pyannote-community-1/speaker-diarization-community-1 pytest -m slow
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def test_pipeline_loads_offline_without_a_token(tmp_path):
    model_dir = os.environ.get("AUTOTRANSCRIPT_MODEL_DIR")
    if not model_dir:
        pytest.skip("AUTOTRANSCRIPT_MODEL_DIR n'est pas défini")
    if not (Path(model_dir) / "config.yaml").is_file():
        pytest.skip(f"pas de config.yaml dans {model_dir}")
    pytest.importorskip("pyannote.audio")

    env = {k: v for k, v in os.environ.items() if k not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")}
    env.update(HF_HUB_OFFLINE="1", PYANNOTE_METRICS_ENABLED="false",
               HOME=str(tmp_path), USERPROFILE=str(tmp_path))   # aucun jeton ni cache HuggingFace
    code = ("import sys; from pyannote.audio import Pipeline; "
            "p = Pipeline.from_pretrained(sys.argv[1]); print('OK' if p is not None else 'NONE')")
    result = subprocess.run([sys.executable, "-c", code, str(Path(model_dir).resolve())],
                            env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("OK")
