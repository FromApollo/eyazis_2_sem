// Browser-level verification with a deterministic fake microphone result.
const { chromium } = require("playwright");
const path = require("path");

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    class FakeRecognition {
      constructor() { window.fakeRecognition = this; this.processLocally = false; }
      static async available() { return "available"; }
      start() { this.started = true; }
      stop() { this.started = false; if (this.onend) this.onend(); }
      emit(phrase) {
        this.onresult({ resultIndex: 0, results: [{ 0: { transcript: phrase }, isFinal: true }] });
      }
    }
    window.SpeechRecognition = FakeRecognition;
    window.spokenMessages = [];
    SpeechSynthesis.prototype.cancel = function () {};
    SpeechSynthesis.prototype.speak = function (utterance) {
      window.spokenMessages.push({ text: utterance.text, lang: utterance.lang });
    };
  });

  await page.goto("http://127.0.0.1:5009/");
  await page.screenshot({ path: path.join(__dirname, "report_assets", "01_initial.png"), fullPage: true });
  await page.locator("#language").selectOption("en-GB");
  await page.getByRole("button", { name: "Start listening" }).click();
  if (await page.evaluate(() => window.fakeRecognition.lang) !== "en-GB") throw new Error("Language setting failed");
  await page.evaluate(() => window.fakeRecognition.emit("help"));
  if (!(await page.locator("#status").innerText()).includes("Commands:")) throw new Error("Help failed");
  await page.evaluate(() => window.fakeRecognition.emit("unknown operation"));
  if (!(await page.locator("#status").innerText()).includes("No operation matches")) throw new Error("Unknown command feedback failed");
  await page.evaluate(() => window.fakeRecognition.emit("show plan"));
  if (!(await page.locator("#plan").isVisible())) throw new Error("Spoken Show plan did not react");
  await page.evaluate(() => window.fakeRecognition.emit("dictate"));
  await page.evaluate(() => window.fakeRecognition.emit("In Hamlet, I argue that doubt affects every choice."));
  if (!(await page.locator("#essay").inputValue()).includes("In Hamlet")) throw new Error("Dictation failed");
  await page.locator("#essay").fill("In Shakespeare's Hamlet, I argue that hesitation shapes the hero's decisions. For example, the text shows his uncertainty and conflict.\n\nIn conclusion, Hamlet's doubt changes the course of the tragedy.");
  await page.evaluate(() => window.fakeRecognition.emit("analyze essay"));
  await page.locator("#results").waitFor({ state: "visible" });
  if ((await page.locator("#word-count").innerText()) !== "30") throw new Error("Word count incorrect");
  await page.screenshot({ path: path.join(__dirname, "report_assets", "02_analysis.png"), fullPage: true });
  await page.evaluate(() => window.fakeRecognition.emit("read results"));
  const spoken = await page.evaluate(() => window.spokenMessages);
  if (!spoken.some((item) => item.text.includes("30 words"))) throw new Error("Speech synthesis failed");
  await page.evaluate(() => window.fakeRecognition.emit("clear essay"));
  if (await page.locator("#essay").inputValue()) throw new Error("Clear essay failed");
  await page.evaluate(() => window.fakeRecognition.onerror({ error: "network" }));
  await page.getByText("Local recognition is ready", { exact: false }).waitFor();
  if (!(await page.evaluate(() => window.fakeRecognition.processLocally))) throw new Error("Local recognition retry failed");
  if (errors.length) throw new Error(errors.join("; "));
  console.log("Browser checks passed: commands, dictation, analysis, synthesis, clearing, local recognition fallback, no JS errors.");
  await browser.close();
}

main().catch((error) => { console.error(error); process.exit(1); });
