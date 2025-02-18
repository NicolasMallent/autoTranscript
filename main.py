import datetime
import whisper
import os
import sys

def floatToTime(time_float: float):
    # Convert start time into a format [HH:MM:SS]
    delta = datetime.timedelta(seconds=time_float)
    hours, remainder = divmod(delta.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    time_format = f"{int(hours):02}:{int(minutes):02}:{seconds:06.3f}"
    return time_format


if __name__ == '__main__':
    if "ffmpeg" not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + "C:\\Program Files\\ffmpeg\\bin"

    # Chemin du dossier où se trouve les fichiers audio : les \ deviennent des \\
    dossier = sys.argv[1]
    print("Le dossier des fichiers audio est:", dossier)

    # Récupération des fichiers audio qui sont dans le dossier
    fichiers_audio = [f for f in os.listdir(dossier) if os.path.isfile(os.path.join(dossier, f))]

    # Modèle de vocabulaire : base, medium, large ; sera téléchargé une seule fois
    vocabulaire = sys.argv[2]
    print("Le modèle de vocabulaire utilisé est:", vocabulaire)
    model = whisper.load_model(vocabulaire)

    # Activer l’option pour obtenir des détails, y compris les timings
    options = {"task": "transcribe", "verbose": True, "language": "French"}

    # Pour chaque fichier audio faire la transcription
    for fichier_audio in fichiers_audio:
        # Reconstruction du chemin vers le fichier audio
        chemin_fichier_audio = os.path.join(dossier, fichier_audio)

        print("Fichier en cours de traitement: " + chemin_fichier_audio)

        # Le fichier de sorti (format texte) est sauvegardé à côté des fichiers audio (dans le même dossier)
        filename_without_extension = os.path.basename(chemin_fichier_audio).split(".")[0]
        fichier_sorti = os.path.join(dossier,
                                     "output_" + filename_without_extension + "_" + vocabulaire + ".txt")

        # Transcription
        result = model.transcribe(chemin_fichier_audio, **options)

        # Ecriture dans le fichier txt
        with open(fichier_sorti, "w", encoding="utf-8") as fichier_output_txt:
            for segment in result["segments"]:
                start_time = floatToTime(segment['start'])
                end_time = floatToTime(segment['end'])
                fichier_output_txt.write(
                    "\n[" + start_time + " --> " + end_time + "]" + segment['text'].replace("... ", "...\n").replace(
                        ". ", ".\n").replace("! ", "!\n").replace("? ", "?\n"))
