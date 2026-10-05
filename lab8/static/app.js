const text = document.getElementById('text');
const voice = document.getElementById('voice');
const rate = document.getElementById('rate');
const volume = document.getElementById('volume');
const generate = document.getElementById('generate');
const pause = document.getElementById('pause');
const stop = document.getElementById('stop');
const message = document.getElementById('message');
const speech = window.speechSynthesis;
let utterance = null;
let englishVoices = [];

function updateLabels() {
  document.getElementById('count').textContent = `${text.value.length} / ${text.maxLength}`;
  document.getElementById('rateValue').textContent = `${(Number(rate.value) / 10).toFixed(1)}×`;
  document.getElementById('volumeValue').textContent = `${volume.value}%`;
}
function showMessage(value, error = false) {
  message.className = `mt-3 ${error ? 'text-danger' : 'text-secondary'}`;
  message.textContent = value;
}
function setIdle() {
  generate.disabled = !englishVoices.length;
  pause.disabled = true;
  pause.textContent = 'Pause';
  stop.disabled = true;
}
function loadVoices() {
  englishVoices = speech.getVoices().filter(item => item.lang.toLowerCase().startsWith('en'));
  const previous = voice.value;
  voice.replaceChildren();
  englishVoices.forEach((item, index) => voice.add(new Option(`${item.name} (${item.lang})`, String(index))));
  if (previous && Number(previous) < englishVoices.length) voice.value = previous;
  if (!englishVoices.length) {
    voice.add(new Option('No English voice available', ''));
    showMessage('Install an English browser or Windows voice to read text aloud.', true);
  } else {
    showMessage(`${englishVoices.length} English voice${englishVoices.length === 1 ? '' : 's'} available.`);
  }
  if (!speech.speaking) setIdle();
}

if (!speech || !window.SpeechSynthesisUtterance) {
  voice.replaceChildren(new Option('Speech synthesis is unsupported', ''));
  generate.disabled = true;
  showMessage('This browser does not support speech synthesis. Use a recent Chrome or Edge browser.', true);
} else {
  speech.onvoiceschanged = loadVoices;
  loadVoices();
}

generate.addEventListener('click', () => {
  if (!text.value.trim()) { showMessage('Enter English text before reading.', true); return; }
  const selected = englishVoices[Number(voice.value)];
  if (!selected) { showMessage('Select an English voice.', true); return; }
  speech.cancel();
  utterance = new SpeechSynthesisUtterance(text.value);
  utterance.voice = selected;
  utterance.lang = selected.lang;
  utterance.rate = Number(rate.value) / 10;
  utterance.volume = Number(volume.value) / 100;
  utterance.onstart = () => {
    generate.disabled = true;
    pause.disabled = false;
    stop.disabled = false;
    showMessage('Reading aloud.');
  };
  utterance.onend = () => { setIdle(); showMessage('Reading finished.'); };
  utterance.onerror = event => {
    setIdle();
    if (event.error !== 'canceled' && event.error !== 'interrupted')
      showMessage(`Speech could not be played: ${event.error}.`, true);
  };
  speech.speak(utterance);
});
pause.addEventListener('click', () => {
  if (speech.paused) {
    speech.resume();
    pause.textContent = 'Pause';
    showMessage('Reading aloud.');
  } else {
    speech.pause();
    pause.textContent = 'Resume';
    showMessage('Reading paused.');
  }
});
stop.addEventListener('click', () => {
  speech.cancel();
  setIdle();
  showMessage('Reading stopped.');
});
for (const input of [text, rate, volume]) input.addEventListener('input', updateLabels);
text.addEventListener('input', () => {
  if (message.classList.contains('text-danger') && text.value.trim()) showMessage('Text is ready to read.');
});
updateLabels();
