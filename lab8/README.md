# Literature Reader — laboratory work 8, variant 5

An English text-to-speech web app for literature essays. Flask serves a Bootstrap interface; the browser's Web Speech API reads text aloud with a selected English voice, tempo and volume.

## Run on Windows

1. Install Python 3.10 or newer. Use a current Chrome or Edge browser with an English speech voice.
2. From this folder, run `python -m pip install -r requirements.txt`.
3. Run `python app.py`.
4. Open `http://127.0.0.1:5008`.

Write or paste up to 5000 characters, choose a voice and adjust tempo and volume. Click **Read aloud** to listen; use **Pause** and **Stop** to control playback.

Available voices and their processing depend on the browser and operating system. Bootstrap CSS is loaded from a CDN; basic local styling remains if the CDN is unavailable.
