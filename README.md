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

1. Téléchargez le projet depuis GitHub :  
   `Code > Download ZIP`, puis dézippez le dossier.

2. [ﬀmpeg](https://github.com/BtbN/FFmpeg-Builds/releases)  
Dézippez **autoTranscript/ffmpeg/windows/ffmpeg-master-latest-win64-gpl-shared.zip** et renommer le "ffmpeg" puis copier/coller le dossier dans le dossier `C:\Program Files\` avec les droits d'admin. Une fois fait, vous devriez avoir `C:\Program Files\ffmpeg` qui contient les sous dossiers bin, doc, include, etc..

3. Ouvrez le dossier `installer/`, faites un **clic droit** sur `install.ps1` et choisissez **"Exécuter avec PowerShell"**.

4. L'installateur :
   - installe Python si nécessaire (via `winget`)
   - crée un environnement virtuel local
   - installe toutes les dépendances
   - crée un raccourci **AutoTranscript** sur votre bureau

5. Double-cliquez sur le raccourci pour lancer l'application.

> La première transcription télécharge le modèle Whisper choisi (une seule fois).

### Linux

1. Téléchargez et dézippez le projet, ou clonez-le :
   ```bash
   git clone https://github.com/NicolasMallent/autoTranscript.git
   cd autoTranscript
   ```

2. Lancez l'installateur :
   ```bash
   chmod +x installer/install.sh
   ./installer/install.sh
   ```

3. L'installateur :
   - vérifie Python 3 et installe ffmpeg si absent
   - crée un environnement virtuel local
   - installe toutes les dépendances
   - crée un lanceur `lancer.sh` et une entrée dans le menu applications

4. Démarrez l'application :
   ```bash
   ./lancer.sh
   ```

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


---
---
## Configurer et utiliser Whisper en ligne
### Pour préparer le drive (à faire une seule fois)
#### Sources
- [article](https://kevinstratvert.com/2023/01/19/best-free-speech-to-text-ai-whisper-ai/)
- [vidéo](https://www.youtube.com/watch?v=8SQV-B83tPU)

#### Installer Google Colaboratory 

1. Aller sur [Google Drive](https://drive.google.com/) et créer un compte Google (gratuit), si vous n’en avez pas encore un.
2. Sur le coin en haut à gauche, cliquer sur `New button > More > Connect more apps`.
3. En haut du dialogue, écrire dans la fenêtre de recherche Google Colaboratory et lancer la recherche.
4. Choisir la première option : “Colaboratory”
5. Cliquer sur le bouton Install, puis sur Continue et sur OK pour connecter Google Colaboratory à Google Drive.
6. Colaboratory a été installé.
7. Cliquer sur le bouton `Done` et fermer la fenêtre “Connect more apps”.

#### Configurer Google Colaboratory 

1. Aller sur [Google Drive](https://drive.google.com/) et se connecter à son compte Google.
2. Sur le coin en haut à gauche, cliquer sur `New button > More > Colaboratory`. Ceci ouvre Colaboratory.
3. Sur le coin en haut à gauche, donner un nom au fichier en sélectionnant Untitled.ipynb et en le renommant en quelque chose de plus parlant (p. ex. Transcribe_audio.ipynb).
4. Cliquer sur le menu `Runtime` et sélectionner `Change runtime type` pour ouvrir le dialogue `Notebook settings`
5. Régler le `Hardware accelerator` sur `GPU`. Ceci permet d’utiliser la carte graphique, sur laquelle Whisper AI tourne le mieux. 
> Noter l’adresse du Drive.

### Commandes verbatim pour transcrire 

1. Pour arriver sur mon Drive : https://colab.research.google.com/drive/.....
2. Cliquer sur Transcribe_audio.ipynb
3. Glisser le fichier à traduire dans l’espace fichiers de ce dossier (icône de dossier sur la marge gauche)
4. Pour chaque session d’utilisation, réinstaller whisper :

```
!pip install git+https://github.com/openai/whisper.git
!sudo apt update && sudo apt install ffmpeg
!whisper "Titre.mp3" --model large --language fr
```

### Fichiers résultats à sauvegarder
#### Fichier Titre.json
Format contenant du texte et des balises de temps en java

#### Fichier Titre.srt
Format contenant le numéro de phrase, suivi des balises temporelles, suivi du texte (à ouvrir en UTF8 avec nomenclature pour les accents) :
```
1 00 :00 :00,000 –> 00 :00 :06,000 Dans le bouquin, non, . . .
```

#### Fichier Titre.tsv
Format avec le début en ms, la ﬁn en ms, le texte sur une même ligne (ouvrir en UTF8), un peu comme du csv :
```
0 6000 Dans le bouquin, non, . . .
```

#### Fichier Titre.txt
Format ne contenant que le texte, découpé par des retours à la ligne (UTF8)

#### Fichier Titre.vtt
Format avec balises temporelles et texte à la ligne suivante (UTF8) :
```
00 :00.000 –> 00 :06.000
Dans le bouquin, non, 
```
