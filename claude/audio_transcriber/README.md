# Transcription audio avec identification des locuteurs

Application de bureau (Python + Tkinter) qui transcrit un fichier audio et
identifie automatiquement qui parle, sans connaître les personnes à l'avance
(« Locuteur 1 », « Locuteur 2 », etc.).

Basée sur [Whisper](https://github.com/openai/whisper) (transcription) et
[pyannote.audio](https://github.com/pyannote/pyannote-audio) (identification
des locuteurs, modèle Community-1, licence CC-BY-4.0), via la bibliothèque
[WhisperX](https://github.com/m-bain/whisperX).

## Pour les utilisateurs finaux

1. Installer les dépendances : `pip install -r requirements.txt`
2. Installer [ffmpeg](https://ffmpeg.org/download.html) (nécessaire à Whisper) et s'assurer qu'il est accessible dans le PATH.
3. Lancer l'application : `python main.py`
4. Choisir un fichier audio, ajuster les options si besoin, cliquer sur « Transcrire ».

Au premier lancement, l'application télécharge automatiquement le modèle de
diarisation (quelques dizaines de Mo) depuis l'adresse configurée dans
`config.py`, puis le réutilise pour tous les lancements suivants. Aucun
compte ni token Hugging Face n'est nécessaire côté utilisateur : c'est toi,
le développeur, qui prépares ce modèle une seule fois (voir ci-dessous).

## À faire une seule fois, avant de distribuer l'application

1. Crée un compte gratuit sur [huggingface.co](https://huggingface.co).
2. Va sur la page du modèle
   [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
   et accepte les conditions d'utilisation.
3. Génère un token d'accès (lecture) depuis huggingface.co/settings/tokens.
4. Télécharge le dépôt complet en local :
   ```bash
   git lfs install
   git clone https://hf.co/pyannote/speaker-diarization-community-1 pyannote-model
   # quand on te demande un mot de passe, utilise ton token Hugging Face
   ```
5. Compresse le contenu de ce dossier dans une archive `pyannote-model.zip`.
6. Sur ton dépôt GitHub, crée une **Release** (pas un simple commit) et
   attache ce zip comme asset de la release. Chaque asset peut peser jusqu'à
   2 Gio, sans limite de bande passante — contrairement à Git LFS, dont le
   quota gratuit n'est que de 1 Go/mois.
7. Copie l'URL de téléchargement direct de cet asset et colle-la dans
   `config.py`, à la place de `MODEL_RELEASE_URL`.
8. Pense à créditer pyannote / pyannoteAI quelque part dans l'application ou
   son écran « à propos » (exigence de la licence CC-BY-4.0).

À partir de là, tes utilisateurs n'auront jamais besoin de créer de compte
ni de token : l'application télécharge le modèle directement depuis ta
Release GitHub au premier lancement, puis fonctionne hors-ligne.

## Réglages utiles

- **Précision du modèle Whisper** : `tiny`/`base` sont rapides mais moins
  précis ; `medium`/`large-v3` sont plus lents mais bien plus fiables.
  `small` est un bon compromis par défaut.
- **Nombre de locuteurs** : si tu sais combien de personnes parlent dans
  l'enregistrement, renseigner min/max dans l'interface améliore nettement
  la qualité de l'identification.
- **GPU** : si une carte graphique compatible CUDA est disponible, le
  moteur l'utilise automatiquement (sinon tout tourne sur le processeur,
  plus lentement mais sans configuration particulière).

## Structure du projet

- `main.py` — point d'entrée
- `gui.py` — interface graphique (Tkinter)
- `engine.py` — transcription + diarisation (WhisperX)
- `model_setup.py` — téléchargement/installation du modèle de diarisation
- `config.py` — réglages (chemins, URL du modèle, langues proposées…)
