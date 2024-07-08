
# autoTranscript  
Transcription automatique avec Whisper AI (en local / en ligne)
#### Author : Cécile de Hosson (UPCité - LDAR)  
#### Contributors : Nicolas Mallent (Ingénieur Recherche et Développement Robotique)

## Préambule 
Vous avez le choix entre deux options :   
-   soit installer whisper directement sur votre machine (en local, donc) si vous disposez d’un émulateur PYTHON.  
-   soit (et c’est ce que j’utilise moi) utiliser un émulateur PYTHON en ligne (gg colaboratory).  

## Récupération du projet

Télécharger ce projet en cliquant sur `< > Code > Download ZIP` (Comme montré ci-dessous) :
![Une image descriptive](ressources/Illustration_download.png)

### 1. Configurer et utiliser whisper en local

Whisper est un logiciel libre de OpenAI. La configuration proposée ci-dessous respecte le cadre de la RGDP puisque les transcriptions sont réalisées en “***local***.”

#### 1.1 Configurer whisper

Fichiers à télécharger puis installer :

- python 3.11
    - https://www.python.org/downloads/release/python-3110/
    - Prendre Windows installer (64-bit) 
    - https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe

- ﬀmpeg
    - https://github.com/BtbN/FFmpeg-Builds/releases
    - prendre [ﬀmpeg-master-latest-win64-gpl.zip](https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ﬀmpeg-master-latest-win64-gpl.zip)

- git
    - https://git-scm.com/download/win
    - prendre la version [64-bit Git for Windows Setup](https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/Git-2.43.0-64-bit.exe)
    - laisser coché tout tel quel pendant l’installation

- pycharm : à installer en dernier
    - https://www.jetbrains.com/fr-fr/pycharm/download/download-thanks.html?platform=windows&code=PCC
    - prendre pycharm-community-2023.2.51.2


#### 1.2 Utiliser whisper pour la première fois

- Lancer pycharm
- Créer un nouveau projet pour toutes les transcriptions par whisper :
    -  Donner un nom rappelant sa fonction : « whisper », « transcrire », etc.
    - Vériﬁer que venv est coché
- Clic droit sur le dossier `.venv > New > Python File`, nommez le fichier main.py, par exemple.
  - Copier le **contenu** d'autoTranscript/main.py et collez-le dans le .venv/main.py que vous venez de créer
- Dans le fichier .venv/main.py, si whisper est souligné en rouge :
  - Ouvrir le terminal de l’environnement virtuel venv 
  - Recopier et entrer : `pip install git+https://github.com/openai/whisper.git`
> C'est possible que vous ayez un problème avec numpy, pour le régler, faites:  `pip install numpy<2`

#### 1.3 Utiliser Whisper
> Attention !
> Le chemin et le nom des fichiers ne doivent pas comporter d'espaces, d'accents ou tout autres caractères spéciaux.  
> Privilégiez des `_` ou des `-` pour remplacer les espaces.

##### 1.3.1 Extraction du son d’une vidéo locale

- Télécharger et installer Audacity : 
    - [Audacity](https://www.audacityteam.org/download/windows/)
    - Choisir : 64 bit installer (recommended).
- Ouvrir Audacity.
- Vériﬁer que ﬀmpeg est disponible (une seule fois) :
    - Cliquer sur `Edition > Préférences > Bibliothèques`.
    - Bibliothèque FFmpeg : cliquer sur Localiser... puis, si nécessaire, sur Téléchargement.
- Glisser la vidéo sur l’écran d’Audacity.
- `Fichier > exporter l’audio` : exporter en mp3.

##### 1.3.2 Mise en route de Whisper

- Ouvrir PyCharm, et le projet pour Whisper.
- Aller dans le dossier .venv (environnement virtuel), le sous-dossier du projet.
- Ce script a besoin qu'on lui donne 2 paramètres d'entrées :
  - Le chemin vers le dossier où sont stockés les enregistrements :
      - Dans `Run > Edit Configurations`, remplissez le champ "Script Parameters" avec le chemin de votre dossier (par exemple "C:\Users\admin\Documents\audio")
      - Cliquez sur le bouton `Apply` puis `OK`
      - Pour récupérer le chemin du dossier : clic droit sur la barre du dossier contenant le fichier mp3, puis choisir Copier l’adresse sous forme de texte.
  - Ainsi que le modèle de vocabulaire (pour indiquer à la transcription le modèle de vocabulaire à utiliser) :
      - "base" : petit, téléchargement immédiat (139 M)
      - "medium" : moyen, téléchargement 20 minutes (1.42 G)
      - "large" : grand, téléchargement 1 heure (2,88 G)
- Exécuter main.py

> Le téléchargement du modèle de vocabulaire se fait qu'une fois.

![Une image descriptive](ressources/edit_config.png)

#### 1.4 Récupération des fichiers transcrits

Les fichiers ont pour nom « output_<nom_de_l_audio>_<modele>.txt ». 
Ils sont enregistrés dans le même dossier que l’audio qui a été transcrit.

### 2. Configurer et utiliser Whisper en ligne
#### 2.1 Pour préparer le drive (à faire une seule fois)
##### 2.1.1 Sources
- [article](https://kevinstratvert.com/2023/01/19/best-free-speech-to-text-ai-whisper-ai/)
- [vidéo](https://www.youtube.com/watch?v=8SQV-B83tPU)

##### 2.1.2 Installer Google Colaboratory 

1. Aller sur [Google Drive](https://drive.google.com/) et créer un compte Google (gratuit), si vous n’en avez pas encore un.
2. Sur le coin en haut à gauche, cliquer sur `New button > More > Connect more apps`.
3. En haut du dialogue, écrire dans la fenêtre de recherche Google Colaboratory et lancer la recherche.
4. Choisir la première option : “Colaboratory”
5. Cliquer sur le bouton Install, puis sur Continue et sur OK pour connecter Google Colaboratory à Google Drive.
6. Colaboratory a été installé.
7. Cliquer sur le bouton `Done` et fermer la fenêtre “Connect more apps”.

##### 2.1.3 Configurer Google Colaboratory 

1. Aller sur [Google Drive](https://drive.google.com/) et se connecter à son compte Google.
2. Sur le coin en haut à gauche, cliquer sur `New button > More > Colaboratory`. Ceci ouvre Colaboratory.
3. Sur le coin en haut à gauche, donner un nom au fichier en sélectionnant Untitled.ipynb et en le renommant en quelque chose de plus parlant (p. ex. Transcribe_audio.ipynb).
4. Cliquer sur le menu `Runtime` et sélectionner `Change runtime type` pour ouvrir le dialogue `Notebook settings`
5. Régler le `Hardware accelerator` sur `GPU`. Ceci permet d’utiliser la carte graphique, sur laquelle Whisper AI tourne le mieux. 
> Noter l’adresse du Drive.

#### 2.2 Commandes verbatim pour transcrire 

1. Pour arriver sur mon Drive : https://colab.research.google.com/drive/.....
2. Cliquer sur Transcribe_audio.ipynb
3. Glisser le fichier à traduire dans l’espace fichiers de ce dossier (icône de dossier sur la marge gauche)
4. Pour chaque session d’utilisation, réinstaller whisper :

```
!pip install git+https://github.com/openai/whisper.git
!sudo apt update && sudo apt install ffmpeg
!whisper "Titre.mp3" --model large --language fr
```

#### 2.3 Fichiers résultats à sauvegarder
##### 2.3.1 Fichier Titre.json
Format contenant du texte et des balises de temps en java

##### 2.3.2 Fichier Titre.srt
Format contenant le numéro de phrase, suivi des balises temporelles, suivi du texte (à ouvrir en UTF8 avec nomenclature pour les accents) :
```
1 00 :00 :00,000 –> 00 :00 :06,000 Dans le bouquin, non, . . .
```

##### 2.3.3 Fichier Titre.tsv
Format avec le début en ms, la ﬁn en ms, le texte sur une même ligne (ouvrir en UTF8), un peu comme du csv :
```
0 6000 Dans le bouquin, non, . . .
```

##### 2.3.4 Fichier Titre.txt
Format ne contenant que le texte, découpé par des retours à la ligne (UTF8)

##### 2.3.5 Fichier Titre.vtt
Format avec balises temporelles et texte à la ligne suivante (UTF8) :
```
00 :00.000 –> 00 :06.000
Dans le bouquin, non, 
```
