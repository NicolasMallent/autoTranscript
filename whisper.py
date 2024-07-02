import datetime
import whisper
import os

def floatToTime( time_float : float):
    # Convert start time into a format [HH:MM:SS]
    delta = datetime.timedelta(seconds=time_float)
    hours, remainder = divmod(delta.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    time_format = f"{int(hours):02}:{int(minutes):02}:{seconds:06.3f}"
    return time_format

if __name__ == '__main__':
    if "ffmpeg" not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep +"C:\\Program Files\\ffmpeg-master-latest-win64-gpl\\bin"

    # Chemin du dossier où se trouve les fichiers audio : les \ deviennent des \\
    dossier = ("C:\\Users\\lirdef\\Desktop\\BTC\\Mtp\\texte-carto")

    # Récupération des fichiers audio qui sont dans le dossier
    fichiers_audio = [f for f in os.listdir(dossier) if os.path.isfile(os.path.join(dossier, f))]

    # Modèle de vocabulaire : base, medium, large ; sera téléchargé une seule fois
    vocabulaire = "large"
    model = whisper.load_model(vocabulaire)

    # Activer l’option pour obtenir des détails, y compris les timings
    options = { "task": "transcribe", "verbose": True, "language": "French" }

    # Pour chaque fichier audio faire la transcription
    for fichier_audio in fichiers_audio:
        # Reconstruction du chemin vers le fichier audio
        chemin_fichier_audio = os.path.join(dossier, fichier_audio)

        # Le fichier de sorti (format texte) est sauvegardé à côté des fichiers audio (dans le même dossier)
        fichier_sorti = os.path.join(dossier, "output_" + chemin_fichier_audio.split("\\")[-1] + "" + vocabulaire + ".txt")
        
        # Transcription
        result = model.transcribe(chemin_fichier_audio, **options)

        # Ecriture dans le fichier txt
        with open(fichier_sorti, "w", encoding="utf-8") as fichier_output_txt:
            for segment in result["segments"]:
                start_time = floatToTime(segment['start'])
                end_time = floatToTime(segment['end'])
                fichier_output_txt.write("\n[" + start_time + " --> " + end_time + "]" + segment['text'].replace("... ", "...\n").replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n"))
