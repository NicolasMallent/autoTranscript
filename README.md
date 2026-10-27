# AutoTranscript

[![GitHub](https://img.shields.io/badge/GitHub-NicolasMallent%2FautoTranscript-blue?logo=github)](https://github.com/NicolasMallent/autoTranscript)

Application de **transcription automatique** de fichiers audio et vidéo, utilisant [WhisperX](https://github.com/m-bain/whisperX) (basé sur Whisper AI d'OpenAI) et [pyannote.audio](https://github.com/pyannote/pyannote-audio) pour l'identification des locuteurs.  
Toutes les transcriptions sont réalisées **entièrement en local** — aucune donnée n'est envoyée sur internet. Conforme au **RGPD**.

---

## Fonctionnalités

- Interface graphique simple (français / anglais)
- Transcription d'un fichier unique ou de tout un dossier
- Accepte les fichiers **audio** (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac`) et **vidéo** (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`)
- **Identification automatique des locuteurs** (Locuteur 1, Locuteur 2…) avec nombre min/max configurable
- Choix du modèle IA selon vos besoins (rapidité vs qualité)
- Formats de sortie : `.txt` horodaté, `.txt` avec locuteurs, `.srt` (sous-titres synchronisés) et/ou `.json`
- Fonctionne sur **Windows 11** et **Linux**

---

## Prérequis

**Aucun.** L'installateur prend en charge tout automatiquement.

---

## Installation

### Windows 11

1. Rendez-vous sur la page [**Releases**](https://github.com/NicolasMallent/autoTranscript/releases/latest) du dépôt GitHub.
2. Téléchargez **`AutoTranscript-Setup-Windows.exe`**.
3. Double-cliquez sur le fichier téléchargé et suivez l'assistant d'installation.

L'installateur prend en charge automatiquement :
- Python (version autonome, n'interfère pas avec votre système)
- ffmpeg (inclus dans l'installateur)
- Toutes les dépendances IA (~3 Go téléchargés lors de l'installation)
- Un raccourci sur le Bureau et dans le Menu Démarrer

> Aucun droit administrateur requis. Aucune configuration manuelle.

### Linux (Debian / Ubuntu)

1. Rendez-vous sur la page [**Releases**](https://github.com/NicolasMallent/autoTranscript/releases/latest) du dépôt GitHub.
2. Téléchargez **`autotranscript_*.deb`**.
3. Installez le paquet :
   ```bash
   sudo apt install ./autotranscript_*.deb
   ```

Le paquet installe automatiquement les dépendances système (`python3-venv`, `python3-tk`, `ffmpeg`) puis télécharge les dépendances IA (~3 Go).

4. Lancez l'application depuis le menu applications ou en ligne de commande :
   ```bash
   autotranscript
   ```

<details>
<summary>Installation manuelle (développeurs)</summary>

```bash
git clone https://github.com/NicolasMallent/autoTranscript.git
cd autoTranscript
chmod +x installer/install.sh
./installer/install.sh
# puis :
./lancer.sh
```

Tests (aucun modèle ni GPU requis : whisperx est simulé) :

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/                  # tout
.venv/bin/python -m pytest tests/unit              # tests unitaires
.venv/bin/python -m pytest tests/functional        # scénarios complets
# test lent avec le vrai modèle de diarisation, hors ligne et sans token :
AUTOTRANSCRIPT_MODEL_DIR=pyannote-community-1/speaker-diarization-community-1 .venv/bin/python -m pytest -m slow
```
</details>

---

## Utilisation

1. **Sélectionnez la source** : choisissez entre *Fichier unique* (audio ou vidéo) ou *Dossier* (tous les fichiers compatibles du dossier seront traités).

2. **Choisissez le modèle IA** selon vos besoins :

   | Modèle    | Taille  | Qualité      | Vitesse      |
   |-----------|---------|--------------|--------------|
   | tiny      | 75 MB   | Basique      | Très rapide  |
   | base      | 139 MB  | Correcte     | Rapide       |
   | small     | 461 MB  | Bonne        | Moyenne      |
   | medium    | 1.4 GB  | Très bonne   | Lente        |
   | large     | 2.9 GB  | Excellente   | Très lente   |
   | large-v2  | 2.9 GB  | Très bonne   | Très lente   |
   | large-v3  | 2.9 GB  | Meilleure    | Très lente   |

   > Le modèle est téléchargé automatiquement lors de la première utilisation, puis mis en cache localement.

3. **Choisissez la langue** de transcription (Français, English, ou détection automatique).

4. **Identification des locuteurs** (cochée par défaut) : l'application détecte automatiquement les changements d'interlocuteur et étiquette chaque prise de parole (*Locuteur 1*, *Locuteur 2*…).  
   Vous pouvez indiquer le nombre minimum et maximum de locuteurs si vous le connaissez.  
   > Au premier usage, l'application télécharge le modèle de diarisation (~35 Mo) depuis les Releases de ce dépôt et le met en cache. Aucun compte HuggingFace n'est nécessaire.

5. **Sélectionnez le(s) format(s) de sortie** souhaités.

6. Cliquez sur **Transcrire**. Les fichiers résultats sont enregistrés **dans le même dossier** que la source.
   La barre de progression avance sur l'ensemble des fichiers, et une ligne du journal indique l'avancement de l'étape en cours (transcription, puis identification des locuteurs) avec, pour la transcription, une estimation du temps restant affichée une fois le rythme établi (la progression de l'identification des locuteurs n'étant pas régulière, elle n'indique qu'un pourcentage). Le premier lancement d'un modèle peut être long : il est d'abord téléchargé.

---

## Formats de sortie

### `.txt` sans identification des locuteurs

Une ligne par **phrase**, avec ses temps de début et de fin (obtenus par alignement des mots sur l'audio) :

```
[00:00:00.031 --> 00:00:06.240] Dans le bouquin, non, il y a une partie sur la lumière.
[00:00:06.500 --> 00:00:11.100] Exactement, c'est ce dont je voulais parler.
```

> Si l'alignement est impossible (langue sans modèle d'alignement, modèle non téléchargeable), l'application l'indique et revient à un horodatage par bloc de parole Whisper, plus long (plusieurs phrases par ligne).

### `.txt` avec identification des locuteurs

```
Locuteur 1 [00:00:00 - 00:00:06] : Dans le bouquin, non, il y a une partie sur la lumière.

Locuteur 2 [00:00:06 - 00:00:11] : Exactement, c'est ce dont je voulais parler.
```

Un passage que l'identification n'a pu attribuer à personne est étiqueté **Locuteur ?** (il n'est pas compté comme un locuteur supplémentaire). Les libellés suivent la langue de l'interface (*Speaker 1*… en anglais).

### `.srt` (sous-titres)

Format standard compatible VLC, DaVinci Resolve, Word, etc. Permet de réécouter l'enregistrement avec les sous-titres qui défilent automatiquement.

```
1
00:00:00,000 --> 00:00:06,240
Locuteur 1 : Dans le bouquin, non, il y a une partie sur la lumière.

2
00:00:06,500 --> 00:00:11,100
Locuteur 2 : Exactement, c'est ce dont je voulais parler.
```

### `.json` (données brutes)

Tous les segments avec métadonnées (timestamps, locuteurs, langue détectée…). Utile pour un traitement ultérieur par programme.

---

## Note RGPD

AutoTranscript fonctionne **entièrement hors ligne** une fois les modèles téléchargés. Les fichiers audio/vidéo et les transcriptions ne quittent jamais votre ordinateur. Aucune connexion à un service tiers n'est établie pendant la transcription.

Seuls des **modèles et données publics** sont téléchargés, au premier usage : modèles Whisper et d'alignement des mots, modèle de diarisation (depuis les Releases de ce dépôt) et données de découpage en phrases de NLTK (installées dans `~/.autotranscript/nltk_data`, ou à l'installation du paquet `.deb`). Si ces dernières ne peuvent pas être téléchargées, la transcription continue avec un horodatage par segment au lieu d'un horodatage par phrase.

---

## Auteurs

Ce projet a été initié et développé par :

- **Cécile de Hosson** — UPCité, Laboratoire de Didactique André Revuz (LDAR)
- **Sylviane Pompéï** — UPCité, Laboratoire de Didactique André Revuz (LDAR)
- **Pierre Andrieu** — UPCité, Laboratoire de Didactique André Revuz (LDAR)

Contributeur :

- **Nicolas Mallent** — Ingénieur Recherche et Développement Robotique

---

## Crédits et licences tierces

| Composant | Auteurs | Licence |
|-----------|---------|---------|
| [Whisper AI](https://github.com/openai/whisper) | OpenAI | MIT |
| [WhisperX](https://github.com/m-bain/whisperX) | Max Bain et al. | BSD-4 |
| [pyannote.audio](https://github.com/pyannote/pyannote-audio) | Hervé Bredin et al., pyannoteAI | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) (modèle) | Hervé Bredin et al., pyannoteAI | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [ffmpeg](https://ffmpeg.org) | FFmpeg team | LGPL / GPL |

L'utilisation du modèle de diarisation **pyannote.audio** est soumise à la licence [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Conformément à cette licence, le crédit suivant est requis :

> *Bredin, H., et al. (2023). pyannote.audio 2.1 speaker diarization pipeline. pyannoteAI.*

Le modèle `pyannote/speaker-diarization-community-1` est **redistribué sans modification** dans les [Releases](https://github.com/NicolasMallent/autoTranscript/releases) de ce dépôt (fichier `pyannote-community-1.zip`, avec son empreinte SHA-256 et un fichier `LICENSE-NOTICE.txt`), conformément à sa licence CC BY 4.0. Source : [huggingface.co/pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1).

---

## Journal (log) et assistance

L'application écrit un journal dans `~/.autotranscript/logs/autotranscript.log` (sous Windows : `%USERPROFILE%\.autotranscript\logs`). En cas de problème, joignez ce fichier à votre signalement : les noms de fichiers et les tokens n'y sont pas enregistrés. L'onglet **Paramètres** permet d'ouvrir le dossier des logs et d'activer un mode debug plus détaillé.

---

## Dépôt

[https://github.com/NicolasMallent/autoTranscript](https://github.com/NicolasMallent/autoTranscript)
