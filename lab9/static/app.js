"use strict";

const $ = (id) => document.getElementById(id);
const essay = $("essay");
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
let recognition = null;
let listening = false;
let dictationNext = false;
let lastResult = null;

function notify(message, kind = "info", spoken = false) {
  const status = $("status");
  status.textContent = message;
  status.className = `alert alert-${kind}`;
  if (spoken) speak(message);
}

function speak(text) {
  if (!canSpeak) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = $("language").value;
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
}

function updateCharacters() {
  $("characters").textContent = `${essay.value.length} / 10000 characters`;
}

function resultSpeech(data) {
  const found = Object.values(data.markers).filter(Boolean).length;
  return `${data.word_count} words, ${data.sentence_count} sentences, ${data.paragraph_count} paragraphs. ${found} of 3 structure signals found.`;
}

function showResults(data) {
  lastResult = data;
  $("results").hidden = false;
  $("word-count").textContent = data.word_count;
  $("sentence-count").textContent = data.sentence_count;
  $("paragraph-count").textContent = data.paragraph_count;
  const labels = { thesis: "Thesis phrase", evidence: "Evidence phrase", conclusion: "Conclusion phrase" };
  $("markers").replaceChildren();
  for (const [key, label] of Object.entries(labels)) {
    const item = document.createElement("li");
    item.textContent = `${label}: ${data.markers[key] ? "found" : "not found"}`;
    $("markers").append(item);
  }
  $("top-words").textContent = data.top_words.length
    ? data.top_words.map((item) => `${item.word} (${item.count})`).join(", ")
    : "No content words found.";
}

async function analyzeEssay() {
  if (!essay.value.trim()) {
    notify("Enter or dictate an essay first.", "warning", true);
    return;
  }
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: essay.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Analysis failed.");
    showResults(data);
    notify(`Analysis complete. ${resultSpeech(data)}`, "success", true);
  } catch (error) {
    notify(error.message, "danger", true);
  }
}

function clearEssay() {
  essay.value = "";
  lastResult = null;
  $("results").hidden = true;
  updateCharacters();
  notify("Essay cleared.", "success", true);
}

function runCommand(phrase) {
  const command = phrase.toLowerCase().replace(/[.!?]+$/g, "").trim();
  if (dictationNext) {
    essay.value = [essay.value.trim(), phrase.trim()].filter(Boolean).join(" ").slice(0, 10000);
    dictationNext = false;
    updateCharacters();
    notify("Dictation added to the essay.", "success", true);
  } else if (command === "analyze essay") {
    analyzeEssay();
  } else if (command === "dictate") {
    dictationNext = true;
    notify("Dictation mode: say one phrase now.", "info", true);
  } else if (command === "read results") {
    if (lastResult) {
      notify("Reading the last analysis.", "info");
      speak(resultSpeech(lastResult));
    } else {
      notify("Analyze an essay first.", "warning", true);
    }
  } else if (command === "show plan") {
    $("plan").hidden = false;
    notify("Essay plan displayed: introduction, body with evidence, conclusion.", "success", true);
  } else if (command === "clear essay") {
    clearEssay();
  } else if (command === "help") {
    notify("Commands: analyze essay, dictate, read results, show plan, clear essay, help.", "info", true);
  } else {
    notify(`No operation matches “${phrase}”. Say “Help” for the list.`, "warning", true);
  }
}

function setListening(active) {
  listening = active;
  $("listen").disabled = active;
  $("stop").disabled = !active;
}

if (!Recognition) {
  $("listen").disabled = true;
  notify("Speech recognition is unavailable in this browser. Text analysis still works.", "warning");
} else {
  recognition = new Recognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = (event) => {
    // Do not mistake the application's spoken feedback for a new command.
    if (canSpeak && window.speechSynthesis.speaking) return;
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const phrase = event.results[i][0].transcript.trim();
      $("transcript").textContent = phrase;
      if (event.results[i].isFinal && phrase) runCommand(phrase);
    }
  };
  recognition.onerror = async (event) => {
    if (event.error === "network") {
      // Some Chromium builds require an online recognition service. A newer
      // browser may also offer an already installed local English language pack.
      if (typeof Recognition.available === "function" && "processLocally" in recognition) {
        try {
          const availability = await Recognition.available({
            langs: [recognition.lang], processLocally: true,
          });
          if (availability === "available") {
            recognition.processLocally = true;
            notify("Online speech recognition is unavailable. Local recognition is ready; press Start listening again.", "warning");
            return;
          }
        } catch (_) {
          // The optional local API may be blocked by this browser.
        }
      }
      notify("Speech recognition could not reach its service. Open this page in Chrome or Edge and check internet access. Text analysis still works.", "warning");
    } else if (event.error === "not-allowed" || event.error === "audio-capture") {
      notify("Microphone access is unavailable. Allow microphone access for this page and try again.", "danger");
    } else {
      notify(`Speech recognition error: ${event.error}.`, "danger");
    }
  };
  recognition.onend = () => {
    setListening(false);
    if ($("status").classList.contains("alert-info")) notify("Listening stopped.");
  };
  $("listen").addEventListener("click", () => {
    recognition.lang = $("language").value;
    try {
      recognition.start();
      setListening(true);
      notify("Listening for an English command…");
    } catch (error) {
      notify(`Could not start recognition: ${error.message}`, "danger");
    }
  });
  $("stop").addEventListener("click", () => recognition.stop());
}

$("analyze").addEventListener("click", analyzeEssay);
$("clear").addEventListener("click", clearEssay);
essay.addEventListener("input", () => {
  lastResult = null;
  $("results").hidden = true;
  updateCharacters();
});
$("language").addEventListener("change", () => notify(`Language selected: ${$("language").selectedOptions[0].text}.`));
updateCharacters();
