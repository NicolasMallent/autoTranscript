# AutoTranscript

[![GitHub](https://img.shields.io/badge/GitHub-NicolasMallent%2FautoTranscript-blue?logo=github)](https://github.com/NicolasMallent/autoTranscript)

Application de **transcription automatique** de fichiers audio et vidéo, utilisant [Whisper AI](https://github.com/openai/whisper) d'OpenAI.  
Toutes les transcriptions sont réalisées **entièrement en local** — aucune donnée n'est envoyée sur internet. Conforme au **RGPD**.

---

## Fonctionnalités

- Interface graphique simple (français / anglais)
- Transcription d'un fichier unique ou de tout un dossier
- Accepte les fichiers **audio** (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac`) et **vidéo** (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`)
- Choix du modèle IA selon vos besoins (rapidité vs qualité)
- Formats de sortie : `.txt` horodaté et/ou `.json` brut Whisper
- Fonctionne sur **Windows 11** et **Linux**

---

## Prérequis

**Aucun.** L'installateur prend en charge tout automatiquement.

> Sur Windows 11, `winget` est requis (installé par défaut sur Windows 11).  
> Sur Linux, `sudo` est nécessaire pour installer ffmpeg si absent.

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
</details>

---

## Utilisation

1. **Sélectionnez la source** : choisissez entre *Fichier unique* (audio ou vidéo) ou *Dossier* (tous les fichiers compatibles du dossier seront traités).

2. **Choisissez le modèle IA** selon vos besoins :

   | Modèle  | Taille  | Qualité | Vitesse |
   |---------|---------|---------|---------|
   | tiny    | 75 MB   | Basique | Très rapide |
   | base    | 139 MB  | Correcte | Rapide |
   | small   | 461 MB  | Bonne | Moyenne |
   | medium  | 1.4 GB  | Très bonne | Lente |
   | large   | 2.9 GB  | Excellente | Très lente |

   > Le modèle est téléchargé automatiquement lors de la première utilisation, puis mis en cache localement.

3. **Choisissez la langue** de transcription (Français, English, ou détection automatique).

4. **Sélectionnez le(s) format(s) de sortie** souhaités.

5. Cliquez sur **Transcrire**. Les fichiers résultats sont enregistrés **dans le même dossier** que la source, sous la forme :
   - `nom_du_fichier_<modèle>.txt`
   - `nom_du_fichier_<modèle>.json`

---

## Formats de sortie

### `.txt` horodaté

Texte découpé par segment avec les temps de début et de fin :

```
[00:00:00.000 --> 00:00:06.240] Dans le bouquin, non,
il y a une partie sur la lumière.

[00:00:06.500 --> 00:00:11.100] Exactement, c'est ce dont je voulais parler.
```

### `.json` (données brutes Whisper)

Toutes les métadonnées retournées par Whisper : segments, scores de confiance, langue détectée, etc. Utile pour un traitement ultérieur par programme.

---

## Note RGPD

AutoTranscript fonctionne **entièrement hors ligne**. Les fichiers audio/vidéo et les transcriptions ne quittent jamais votre ordinateur. Aucune connexion à un service tiers n'est établie pendant la transcription.

---

## Auteurs

Ce projet a été initié et développé par :

- **Cécile de Hosson** — UPCité, Laboratoire de Didactique André Revuz (LDAR)
- **Sylviane Pompéï** — UPCité, Laboratoire de Didactique André Revuz (LDAR)
- **Pierre Andrieu** — UPCité, Laboratoire de Didactique André Revuz (LDAR)

Contributeur :

- **Nicolas Mallent** — Ingénieur Recherche et Développement Robotique

---

## Dépôt

[https://github.com/NicolasMallent/autoTranscript](https://github.com/NicolasMallent/autoTranscript)

---

## Licence

Ce projet utilise [Whisper AI](https://github.com/openai/whisper) (MIT License, OpenAI).


