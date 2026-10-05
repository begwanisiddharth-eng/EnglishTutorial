/* ============================================================
   State
   ============================================================ */
let todayStr = "";
let activeDates = new Set();
let allEntries = [];
const known = new Map();      // entry id -> entry, for instant drawer headers
let activeId = null;
let focusBeforeDrawer = null;
let drawerContext = "today";  // "today" | "browse" | "all"
let calYear = 0, calMonth = 0, selectedDate = null;

const SPEAKER_ICON = `<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
  <path fill="currentColor" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z"/>
</svg>`;

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
/** Speak text aloud, preferring a British English voice. */
function speak(text) {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-GB";
  utterance.voice = speechSynthesis.getVoices().find((v) => v.lang === "en-GB") ?? null;
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
}

/** Return HTML for the respelling (if any) followed by an audio button. */
function pronunciationHTML(entry) {
  const respelling = entry.respelling ? `<span>${esc(entry.respelling)}</span>` : "";
  return `${respelling}
    <button class="speak" type="button" title="Listen" aria-label="Listen to ${esc(entry.entry)}"
            data-speak="${esc(entry.entry)}">${SPEAKER_ICON}</button>`;
}

// Capture phase, so the click plays audio without also opening the card underneath.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-speak]");
  if (!button) return;
  event.stopPropagation();
  speak(button.dataset.speak);
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

function cardHTML(entry, context) {
  const badge = entry.accepted ? '<span class="card-badge">accepted</span>' : "";
  return `
    <div class="card" id="card-${entry.id}">
      ${badge}
      <button class="card-word card-open" type="button" onclick="openDrawer(${entry.id}, '${context}')">${esc(entry.entry)}</button>
      <div class="pronunciation">${pronunciationHTML(entry)}</div>
      <div class="card-def">${esc(entry.meaning)}</div>
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

function renderList() {
  const query = document.getElementById("search").value.toLowerCase();
  const shown = allEntries.filter((e) =>
    e.entry.toLowerCase().includes(query) || e.meaning.toLowerCase().includes(query));
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
  document.getElementById("d-pron").innerHTML = pronunciationHTML(entry);
  document.getElementById("d-ipa").textContent = entry.pronunciation ? `IPA: ${entry.pronunciation}` : "";
  document.getElementById("d-def").textContent = entry.meaning;
}

function tagsHTML(words, kind) {
  return `<div class="word-tags">${words.map((w) => `<span class="word-tag ${kind}">${esc(w)}</span>`).join("")}</div>`;
}

/** Return HTML for one example with its source: a linked Guardian article or a written example. */
function exampleHTML(example) {
  const source = example.source
    ? `<a href="${esc(example.url)}" target="_blank" rel="noopener">${esc(example.source)}, ${fmtDate(example.date)}</a>`
    : "Example sentence";
  const kind = example.source ? "quote" : "written";
  return `<div class="example-item ${kind}"><div>${esc(example.text)}</div>
    <div class="example-source">&mdash; ${source}</div></div>`;
}

function renderDetail(detail) {
  const senses = detail.senses.map((s) =>
    `<li><span class="pos">${esc(s.part_of_speech)}</span>${esc(s.definition)}</li>`).join("");
  const examples = detail.examples.map(exampleHTML).join("");
  let html = `<div class="section-label">Meanings</div><ol class="senses">${senses}</ol>
    <div class="section-label">Examples</div>${examples}`;
  if (detail.synonyms.length) html += `<div class="section-label">Synonyms</div>${tagsHTML(detail.synonyms, "synonym")}`;
  if (detail.antonyms.length) html += `<div class="section-label">Antonyms</div>${tagsHTML(detail.antonyms, "antonym")}`;
  document.getElementById("d-body").innerHTML = html;
}

/** Enable feedback, Edit and Accept only for today's loaded, unaccepted entries. */
function setFooter(entry, context, loaded) {
  const editable = context !== "browse" && entry.day === todayStr && !entry.accepted && loaded;
  ["d-feedback", "d-edit", "d-accept"].forEach((id) => { document.getElementById(id).disabled = !editable; });
  document.getElementById("d-accepted").hidden = !entry.accepted;
  document.getElementById("d-delete").hidden = context === "browse";
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
  setFooter(known.get(entryId), context, false);
  document.getElementById("d-body").innerHTML =
    '<div class="empty">Finding Guardian examples and preparing meanings...</div>';
  document.getElementById("overlay").classList.add("open");
  document.getElementById("drawer").classList.add("open");
  setModal(true);
  document.querySelector("#drawer .btn-close").focus();
  try {
    const entry = await api(`/api/entries/${entryId}/detail`);
    known.set(entryId, entry);
    if (activeId !== entryId) return;
    renderDetail(entry.detail);
    setFooter(entry, context, true);
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
  await withSpinner("d-edit", async () => {
    const entry = await api(`/api/entries/${entryId}/revise`, "POST", { feedback });
    known.set(entryId, entry);
    refreshCard(entry);
    if (activeId === entryId) {
      renderHeader(entry);
      renderDetail(entry.detail);
      document.getElementById("d-feedback").value = "";
    }
    toast("Entry revised.");
  });
  if (activeId === entryId) setFooter(known.get(entryId), drawerContext, true);
}

/** Accept the open entry as final. */
async function acceptActive() {
  const entryId = activeId;
  await withSpinner("d-accept", async () => {
    const entry = await api(`/api/entries/${entryId}/accept`, "POST");
    known.set(entryId, entry);
    refreshCard(entry);
    toast(`"${entry.entry}" accepted.`);
  });
  if (activeId === entryId) setFooter(known.get(entryId), drawerContext, true);
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
  deleteEntry(activeId, drawerContext);
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
