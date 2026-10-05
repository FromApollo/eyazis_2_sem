# Laboratory work 9 — variant 5

Flask application for analysis of spoken English commands in the domain of literature essays. Web Speech API recognizes commands through `SpeechRecognition`/`webkitSpeechRecognition` and announces actions through `speechSynthesis` and `SpeechSynthesisUtterance`. Flask calculates transparent rule-based essay indicators.

## Run

1. Install Python 3.10 or newer and run `python -m pip install -r requirements.txt`.
2. Run `python app.py`.
3. Open `http://127.0.0.1:5009` in Chrome or Edge and allow microphone access.

Use an English recognition language, then say one of the operations listed in the interface. “Dictate” adds the following recognized phrase to the essay. You can also paste text and click **Analyze essay**. Recognition availability, synthesis voices, and microphone permissions depend on the browser and operating system. Bootstrap 5.3.3 is included locally, so the interface does not depend on a CSS CDN.

If the browser reports a speech recognition `network` error, its recognition service is unavailable. Try the same local URL in current Chrome or Edge with internet access. Where the browser supports on-device Web Speech recognition and has the English language pack installed, the app offers a local retry. Text analysis and speech synthesis remain usable without recognition.
