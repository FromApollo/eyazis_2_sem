const text = document.getElementById('text');
const voice = document.getElementById('voice');
const rate = document.getElementById('rate');
const volume = document.getElementById('volume');
const generate = document.getElementById('generate');
const pause = document.getElementById('pause');
const stop = document.getElementById('stop');
const message = document.getElementById('message');
const speech = window.speechSynthesis;

let englishVoices = [];
let chunks = [];
let chunkIndex = 0;
let isReading = false;
let isPaused = false;
let runId = 0;
let settingsPending = false;

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
  isReading = false;
  isPaused = false;
  generate.disabled = !englishVoices.length;
  pause.disabled = true;
  pause.textContent = 'Pause';
  stop.disabled = true;
}

function setReading() {
  isReading = true;
  isPaused = false;
  generate.disabled = true;
  pause.disabled = false;
  pause.textContent = 'Pause';
  stop.disabled = false;
}

function selectedVoice() {
  return englishVoices[Number(voice.value)];
}

function splitIntoChunks(source) {
  return source.match(/[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$/g) || [];
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
  } else if (!isReading) {
    showMessage(`${englishVoices.length} English voice${englishVoices.length === 1 ? '' : 's'} available.`);
  }
  if (!isReading) setIdle();
}

function speakCurrentChunk(settingsChanged = false) {
  if (chunkIndex >= chunks.length) {
    setIdle();
    showMessage('Reading finished.');
    return;
  }
  const selected = selectedVoice();
  if (!selected) {
    setIdle();
    showMessage('Select an English voice.', true);
    return;
  }

  const currentRun = ++runId;
  speech.cancel();
  const utterance = new SpeechSynthesisUtterance(chunks[chunkIndex]);
  utterance.voice = selected;
  utterance.lang = selected.lang;
  utterance.rate = Number(rate.value) / 10;
  utterance.volume = Number(volume.value) / 100;

  utterance.onstart = () => {
    if (currentRun !== runId) return;
    setReading();
    showMessage(settingsChanged ? 'New settings are applied from this sentence.' : 'Reading aloud.');
  };
  utterance.onend = () => {
    if (currentRun !== runId) return;
    chunkIndex += 1;
    const useNewSettings = settingsPending;
    settingsPending = false;
    speakCurrentChunk(useNewSettings);
  };
  utterance.onerror = event => {
    if (currentRun !== runId || event.error === 'canceled' || event.error === 'interrupted') return;
    setIdle();
    showMessage(`Speech could not be played: ${event.error}.`, true);
  };

  // Chromium requires a short gap between cancel() and the next utterance.
  window.setTimeout(() => {
    if (currentRun === runId) speech.speak(utterance);
  }, 50);
}

function startReading() {
  if (!text.value.trim()) {
    showMessage('Enter English text before reading.', true);
    return;
  }
  if (!selectedVoice()) {
    showMessage('Select an English voice.', true);
    return;
  }
  chunks = splitIntoChunks(text.value);
  chunkIndex = 0;
  speakCurrentChunk();
}

function applyNewSettings() {
  if (isReading) {
    settingsPending = true;
    showMessage('The new settings will be applied from the next sentence.');
  }
}

if (!speech || !window.SpeechSynthesisUtterance) {
  voice.replaceChildren(new Option('Speech synthesis is unsupported', ''));
  generate.disabled = true;
  showMessage('This browser does not support speech synthesis. Use a recent Chrome or Edge browser.', true);
} else {
  speech.onvoiceschanged = loadVoices;
  loadVoices();
}

generate.addEventListener('click', startReading);

pause.addEventListener('click', () => {
  if (!isReading) return;
  if (isPaused) {
    speech.resume();
    window.setTimeout(() => speech.resume(), 50);
    isPaused = false;
    pause.textContent = 'Pause';
    showMessage('Reading aloud.');
  } else {
    speech.pause();
    isPaused = true;
    pause.textContent = 'Resume';
    showMessage('Reading paused.');
  }
});

stop.addEventListener('click', () => {
  ++runId;
  speech.cancel();
  chunkIndex = 0;
  settingsPending = false;
  setIdle();
  showMessage('Reading stopped.');
});

text.addEventListener('input', () => {
  updateLabels();
  if (isReading) {
    ++runId;
    speech.cancel();
    setIdle();
    settingsPending = false;
    showMessage('Text changed. Start reading again.');
  } else if (message.classList.contains('text-danger') && text.value.trim()) {
    showMessage('Text is ready to read.');
  }
});
rate.addEventListener('input', () => {
  updateLabels();
  applyNewSettings();
});
volume.addEventListener('input', () => {
  updateLabels();
  applyNewSettings();
});
voice.addEventListener('change', applyNewSettings);
updateLabels();
