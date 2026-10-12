/* ============================================================
   State
   ============================================================ */
let todayStr = "";
let activeDates = new Set();
let allEntries = [];
const known = new Map();      // entry id -> entry, for instant drawer headers
let activeId = null;
let focusBeforeDrawer = null;
let drawerBusy = false;       // an Edit, Accept or Delete from the drawer is running
let drawerContext = "today";  // "today" | "browse" | "all"
let calYear = 0, calMonth = 0, selectedDate = null;

const SPEAKER_ICON = `<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
  <path fill="currentColor" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z"/>
</svg>`;
const TRASH_ICON = `<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
  <path fill="currentColor" d="M9 3h6l1 2h4v2H4V5h4l1-2zM6 9h12l-1 12H7L6 9zm4 2v8h1.5v-8H10zm2.5 0v8H14v-8h-1.5z"/>
</svg>`;
const SPEECH_TIMEOUT_MS = 5000;
const NETWORK_VOICE_WAIT_MS = 2000;

/* ============================================================
   Helpers
   ============================================================ */
/** Call the API and return parsed JSON, throwing the server's error message on failure. */
async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body) options.body = JSON.stringify(body);
  const response = await fetch(path, options);
  if (response.ok) return response.json();
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : {};
  throw new Error(data.error || `Server error ${response.status}. Check the terminal window for details.`);
}

/** Escape text for safe insertion into HTML. */
function esc(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Format a YYYY-MM-DD date for display. */
function fmtDate(dateStr, options = { day: "numeric", month: "short", year: "numeric" }) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", options);
}

let toastTimer;
/** Show a short message at the bottom of the screen. */
function toast(message, isError = false) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.className = "show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.className = ""; }, 3000);
}

/** Run an async action while showing a spinner on its button. */
async function withSpinner(buttonId, action) {
  const button = document.getElementById(buttonId);
  button.classList.add("loading");
  button.disabled = true;
  try {
    await action();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.classList.remove("loading");
    button.disabled = false;
  }
}

function remember(entries) {
  entries.forEach((entry) => known.set(entry.id, entry));
}

/* ============================================================
   Audio
   ============================================================ */
/** Return the voice to try first: a British voice on this computer, else a British network voice. */
function britishVoice() {
  const british = speechSynthesis.getVoices().filter((v) => v.lang === "en-GB");
  return british.find((v) => v.localService) ?? british[0] ?? null;
}

/** Return an English voice installed on this computer. */
function localVoice() {
  return speechSynthesis.getVoices().find((v) => v.localService && v.lang.startsWith("en")) ?? null;
}

/** Speak text aloud, preferring a British voice; the button shows when speech is playing.
 *  A network voice (Chrome's Google voices) can hang without starting or reporting an error, so if it
 *  has not started after NETWORK_VOICE_WAIT_MS the text is spoken again with an installed voice.
 *  A speech error, or speech that has not started after SPEECH_TIMEOUT_MS, is reported as a toast. */
function speak(text, button, voice = britishVoice()) {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = voice?.lang ?? "en-GB";
  utterance.voice = voice;
  const fallback = voice && !voice.localService ? localVoice() : null;
  const finish = () => {
    clearTimeout(silence);
    button.classList.remove("playing");
  };
  const silence = setTimeout(() => {
    finish();
    if (fallback) {
      utterance.onend = utterance.onerror = null;
      speak(text, button, fallback);
    } else {
      toast(`The browser's speech engine did not start (${speechSynthesis.getVoices().length} voices).`, true);
    }
  }, fallback ? NETWORK_VOICE_WAIT_MS : SPEECH_TIMEOUT_MS);
  utterance.onstart = () => clearTimeout(silence);
  utterance.onend = finish;
  utterance.onerror = (event) => {
    finish();
    if (!["interrupted", "canceled"].includes(event.error)) toast(`Could not play the pronunciation (${event.error}).`, true);
  };
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
  button.classList.add("playing");
}

/** Return HTML for an audio button; with a label it is the side panel's larger Listen button. */
function speakButton(entry, label = "") {
  return `<button class="${label ? "listen" : "speak"}" type="button" title="Listen"
            aria-label="Listen to ${esc(entry.entry)}" data-speak="${esc(entry.entry)}">${SPEAKER_ICON}${
            label ? `<span>${label}</span>` : ""}</button>`;
}

/** Return HTML for the respelling (if any) followed by an audio button. */
function pronunciationHTML(entry) {
  const respelling = entry.respelling ? `<span>${esc(entry.respelling)}</span>` : "";
  return `${respelling}${speakButton(entry)}`;
}

// Capture phase, so the click plays audio without also opening the card underneath.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-speak]");
  if (!button) return;
  event.stopPropagation();
  speak(button.dataset.speak, button);
}, true);

/* ============================================================
   Keyboard
   ============================================================ */
// Enter or Space activates clickable cards, rows and dates; Escape closes the drawer.
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeId !== null) {
    closeDrawer();
  } else if ((event.key === "Enter" || event.key === " ") && event.target.getAttribute("role") === "button") {
    event.preventDefault();
    event.target.click();
  }
});

/* ============================================================
   Navigation
   ============================================================ */
function showView(name) {
  document.querySelectorAll(".view").forEach((v) => { v.hidden = true; });
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById("view-" + name).hidden = false;
  document.getElementById("nav-" + name).classList.add("active");
  if (name === "all") loadAll();
  if (name === "browse") initCalendar();
}

/* ============================================================
   Cards
   ============================================================ */
function skeletons(count) {
  return Array(count).fill('<div class="card-skeleton"></div>').join("");
}

/** Return HTML for a card; today's cards also get a delete button (past days are read-only). */
function cardHTML(entry, context) {
  const badge = entry.accepted ? '<span class="card-badge">accepted</span>' : "";
  const remove = context === "today"
    ? `<button class="card-delete" type="button" title="Delete" aria-label="Delete ${esc(entry.entry)}"
         onclick="deleteEntry(${entry.id}, 'today')">${TRASH_ICON}</button>`
    : "";
  return `
    <div class="card${remove ? " deletable" : ""}" id="card-${entry.id}">
      ${badge}
      <button class="card-word card-open" type="button" onclick="openDrawer(${entry.id}, '${context}')">${esc(entry.entry)}</button>
      <div class="pronunciation">${pronunciationHTML(entry)}</div>
      <div class="card-def">${esc(entry.meaning)}</div>
      ${remove}
    </div>`;
}

function renderCards(entries, containerId, context, emptyText) {
  remember(entries);
  const container = document.getElementById(containerId);
  container.innerHTML = entries.length
    ? entries.map((e) => cardHTML(e, context)).join("")
    : `<div class="empty">${esc(emptyText)}</div>`;
}

/* ============================================================
   Today
   ============================================================ */
async function loadToday() {
  document.getElementById("today-cards").innerHTML = skeletons(5);
  try {
    const data = await api("/api/today");
    todayStr = data.day;
    document.getElementById("today-heading").textContent =
      fmtDate(todayStr, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    renderCards(data.entries, "today-cards", "today", "No entries today.");
    document.getElementById("today-actions").hidden = false;
  } catch (error) {
    document.getElementById("today-cards").innerHTML = `<div class="empty">${esc(error.message)}
      <div><button class="btn btn-secondary retry" onclick="loadToday()">Try again</button></div></div>`;
  }
}

function addEntry() {
  const input = document.getElementById("add-input");
  const text = input.value.trim();
  if (!text || document.getElementById("add-btn").disabled) return;
  withSpinner("add-btn", async () => {
    const entries = await api("/api/today/add", "POST", { entry: text });
    input.value = "";
    renderCards(entries, "today-cards", "today", "No entries today.");
    toast(`"${text}" added.`);
  });
}

function generateMore() {
  withSpinner("more-btn", async () => {
    const before = document.querySelectorAll("#today-cards .card").length;
    const entries = await api("/api/today/more", "POST");
    renderCards(entries, "today-cards", "today", "No entries today.");
    const added = entries.length - before;
    toast(`${added} more ${added === 1 ? "entry" : "entries"} added.`);
  });
}

/* ============================================================
   Browse
   ============================================================ */
async function refreshDates() {
  activeDates = new Set(await api("/api/days"));
}

async function initCalendar() {
  const now = new Date();
  calYear = now.getFullYear();
  calMonth = now.getMonth();
  await refreshDates();
  renderCalendar();
}

function moveMonth(step) {
  calMonth += step;
  if (calMonth < 0) { calMonth = 11; calYear--; }
  if (calMonth > 11) { calMonth = 0; calYear++; }
  renderCalendar();
}

function renderCalendar() {
  const first = new Date(calYear, calMonth, 1);
  document.getElementById("cal-title").textContent =
    first.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  let html = '<div class="cal-cell"></div>'.repeat(first.getDay());
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${calYear}-${String(calMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const isActive = activeDates.has(ds);
    const cls = "cal-cell " + (isActive ? "active" : "inactive") + (ds === selectedDate ? " selected" : "");
    const click = isActive ? `role="button" tabindex="0" onclick="selectDate('${ds}')"` : "";
    html += `<div class="${cls}" ${click}>${d}</div>`;
  }
  document.getElementById("cal-grid").innerHTML = html;
}

async function selectDate(dateStr) {
  if (dateStr === todayStr) {
    showView("today");
    return;
  }
  selectedDate = dateStr;
  renderCalendar();
  document.getElementById("browse-heading").textContent = fmtDate(dateStr);
  document.getElementById("browse-cards").innerHTML = skeletons(3);
  const entries = await api(`/api/days/${dateStr}`);
  renderCards(entries, "browse-cards", "browse", "No accepted entries on this day.");
}

/* ============================================================
   All words
   ============================================================ */
async function loadAll() {
  allEntries = await api("/api/accepted");
  remember(allEntries);
  renderList();
}

/** Return text lowercased with accents removed, as vocab.fold does on the server. */
function fold(text) {
  return text.toLowerCase().replace(/œ/g, "oe").replace(/æ/g, "ae").normalize("NFKD").replace(/\p{M}/gu, "");
}

function renderList() {
  const query = fold(document.getElementById("search").value);
  const shown = allEntries.filter((e) => fold(e.entry).includes(query) || fold(e.meaning).includes(query));
  document.getElementById("word-list").innerHTML = shown.length
    ? shown.map((e) => `
      <li>
        <button class="wl-word wl-open" type="button" onclick="openDrawer(${e.id}, 'all')">${esc(e.entry)}</button>
        <span class="wl-meaning">${esc(e.meaning)}</span>
        <span class="wl-date">${fmtDate(e.day)}</span>
        <button class="wl-delete" onclick="deleteEntry(${e.id}, 'all')">Delete</button>
      </li>`).join("")
    : '<div class="empty">No accepted entries yet.</div>';
}

/* ============================================================
   Drawer
   ============================================================ */
function renderHeader(entry) {
  document.getElementById("d-word").textContent = entry.entry;
  const respelling = entry.respelling ? `<span class="pron-chip" title="Respelling">${esc(entry.respelling)}</span>` : "";
  const ipa = entry.pronunciation ? `<span class="pron-chip ipa" title="IPA">${esc(entry.pronunciation)}</span>` : "";
  document.getElementById("d-pron").innerHTML = `${respelling}${ipa}${speakButton(entry, "Listen")}`;
  document.getElementById("d-def").textContent = entry.meaning;
}

/** Return HTML for a titled section of the side panel, with an optional count. */
function sectionHTML(title, body, count = null) {
  const badge = count === null ? "" : `<span class="count">${count}</span>`;
  return `<section class="d-section"><h3 class="section-label">${title}${badge}</h3>${body}</section>`;
}

function tagsHTML(words, kind) {
  return `<div class="word-tags">${words.map((w) => `<span class="word-tag ${kind}">${esc(w)}</span>`).join("")}</div>`;
}

/** Return HTML for one example with its source: a linked Guardian article or a written example. */
function exampleHTML(example) {
  const source = example.source
    ? `<a href="${esc(example.url)}" target="_blank" rel="noopener">${esc(example.source)} &middot; ${fmtDate(example.date)}
       <span aria-hidden="true">&#8599;</span></a>`
    : "<span>Example sentence</span>";
  const kind = example.source ? "quote" : "written";
  return `<figure class="example-item ${kind}"><blockquote>${esc(example.text)}</blockquote>
    <figcaption class="example-source">${source}</figcaption></figure>`;
}

function renderDetail(detail) {
  const senses = detail.senses.map((s) =>
    `<li><span class="pos">${esc(s.part_of_speech)}</span>${esc(s.definition)}</li>`).join("");
  const related = [["Synonyms", detail.synonyms, "synonym"], ["Antonyms", detail.antonyms, "antonym"]]
    .filter(([, words]) => words.length)
    .map(([title, words, kind]) => `<div>${sectionHTML(title, tagsHTML(words, kind))}</div>`).join("");
  document.getElementById("d-body").innerHTML =
    sectionHTML("Meanings", `<ol class="senses">${senses}</ol>`, detail.senses.length) +
    sectionHTML("Examples", detail.examples.map(exampleHTML).join(""), detail.examples.length) +
    (related ? `<div class="related">${related}</div>` : "");
}

/** Show the side panel's loading state while an entry's content is fetched or written. */
function renderLoading() {
  document.getElementById("d-body").innerHTML = `<div class="d-loading">
    <p>Finding Guardian examples and preparing meanings...</p>
    <div class="line"></div><div class="line short"></div><div class="block"></div><div class="block"></div></div>`;
}

/** Enable feedback, Edit and Accept only for today's loaded, unaccepted entries, and nothing while busy.
 *  Entries that can never be edited (accepted, or from a past day) hide the controls altogether. */
function setFooter(entry, context) {
  const changeable = context !== "browse" && entry.day === todayStr && !entry.accepted;
  const editable = !drawerBusy && changeable && entry.detail;
  document.getElementById("d-footer").classList.toggle("locked", !changeable);
  ["d-feedback", "d-edit", "d-accept"].forEach((id) => { document.getElementById(id).disabled = !editable; });
  document.getElementById("d-accepted").hidden = !entry.accepted;
  document.getElementById("d-delete").hidden = context === "browse";
  document.getElementById("d-delete").disabled = drawerBusy;
}

/** Run a drawer action with the footer locked, so Edit, Accept and Delete cannot overlap. */
async function drawerAction(action) {
  drawerBusy = true;
  setFooter(known.get(activeId), drawerContext);
  await action();
  drawerBusy = false;
  if (activeId !== null) setFooter(known.get(activeId), drawerContext);
}

/** Redraw a visible card after its entry changed, keeping it highlighted. */
function refreshCard(entry) {
  const card = document.getElementById("card-" + entry.id);
  if (!card) return;
  card.outerHTML = cardHTML(entry, card.closest("#browse-cards") ? "browse" : "today");
  document.getElementById("card-" + entry.id).classList.add("active");
}

/** While the drawer is open only it can be reached; while closed it cannot be reached at all. */
function setModal(open) {
  document.getElementById("drawer").inert = !open;
  document.querySelector("nav").inert = open;
  document.querySelector("main").inert = open;
}

async function openDrawer(entryId, context) {
  if (activeId === null) focusBeforeDrawer = document.activeElement;
  activeId = entryId;
  drawerContext = context;
  document.querySelectorAll(".card").forEach((c) => c.classList.remove("active"));
  document.getElementById("card-" + entryId)?.classList.add("active");
  renderHeader(known.get(entryId));
  document.getElementById("d-feedback").value = "";
  setFooter(known.get(entryId), context);
  renderLoading();
  document.getElementById("d-body").scrollTop = 0;
  document.getElementById("overlay").classList.add("open");
  document.getElementById("drawer").classList.add("open");
  setModal(true);
  document.querySelector("#drawer .btn-close").focus();
  try {
    const entry = await api(`/api/entries/${entryId}/detail`);
    known.set(entryId, entry);
    if (activeId !== entryId) return;
    renderDetail(entry.detail);
    setFooter(entry, context);
  } catch (error) {
    document.getElementById("d-body").innerHTML = `<div class="empty">${esc(error.message)}</div>`;
  }
}

/** Send the learner's feedback and show the revised entry. */
async function reviseActive() {
  const entryId = activeId;
  const feedback = document.getElementById("d-feedback").value.trim();
  if (!feedback) {
    toast("Write what should change first.", true);
    return;
  }
  await drawerAction(() => withSpinner("d-edit", async () => {
    const entry = await api(`/api/entries/${entryId}/revise`, "POST", { feedback });
    known.set(entryId, entry);
    refreshCard(entry);
    if (activeId === entryId) {
      renderHeader(entry);
      renderDetail(entry.detail);
      document.getElementById("d-feedback").value = "";
    }
    toast("Entry revised.");
  }));
}

/** Accept the open entry as final. */
async function acceptActive() {
  const entryId = activeId;
  await drawerAction(() => withSpinner("d-accept", async () => {
    const entry = await api(`/api/entries/${entryId}/accept`, "POST");
    known.set(entryId, entry);
    refreshCard(entry);
    toast(`"${entry.entry}" accepted.`);
  }));
}

function closeDrawer() {
  document.getElementById("overlay").classList.remove("open");
  document.getElementById("drawer").classList.remove("open");
  setModal(false);
  document.querySelectorAll(".card").forEach((c) => c.classList.remove("active"));
  const redrawnCard = document.querySelector(`#card-${activeId} .card-open`);
  activeId = null;
  (focusBeforeDrawer?.isConnected ? focusBeforeDrawer : redrawnCard)?.focus();
  focusBeforeDrawer = null;
}

/** Delete an entry after confirmation and refresh the views that showed it. */
async function deleteEntry(entryId, context) {
  const entry = known.get(entryId);
  const note = entry.accepted
    ? " It will be removed from the PDF. An entry from the word list returns to it; one you typed can be looked up again."
    : "";
  if (!confirm(`Delete "${entry.entry}"?${note}`)) return;
  try {
    await api(`/api/entries/${entryId}`, "DELETE");
    known.delete(entryId);
    if (activeId === entryId) closeDrawer();
    toast(`"${entry.entry}" deleted.`);
    if (context === "all") await loadAll();
    if (entry.day === todayStr) await loadToday();
    if (entry.day === selectedDate) {
      await refreshDates();
      await selectDate(selectedDate);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

function deleteActive() {
  drawerAction(() => deleteEntry(activeId, drawerContext));
}

/* ============================================================
   PDF
   ============================================================ */
/** Open the PDF in a new tab, or explain why there is none yet. */
async function openPdf() {
  const response = await fetch("/api/pdf", { method: "HEAD" });
  if (response.ok) {
    window.open("/api/pdf", "_blank");
  } else {
    await api("/api/pdf").catch((error) => toast(error.message, true));
  }
}

/* ============================================================
   Init
   ============================================================ */
loadToday();

// Tell the server which pages are open, so it can stop when the last one closes.
const PAGE_ID = crypto.randomUUID();
addEventListener("pageshow", () => navigator.sendBeacon(`/api/pages/${PAGE_ID}/open`));
addEventListener("pagehide", () => navigator.sendBeacon(`/api/pages/${PAGE_ID}/close`));
