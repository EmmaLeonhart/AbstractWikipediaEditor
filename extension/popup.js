// Popup logic for the Abstract Wikipedia Article Creator extension

const $ = (sel) => document.querySelector(sel);
const statusEl = $("#status");
let currentWikitext = "";
let currentQid = "";

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = type;
}

// Tab switching
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    $(`#tab-${tab.dataset.tab}`).classList.add("active");
  });
});

// Generate wikitext from QID
$("#btn-generate").addEventListener("click", async () => {
  const qid = $("#qid").value.trim().toUpperCase();
  if (!qid || !/^Q\d+$/.test(qid)) {
    setStatus("Enter a valid QID (e.g. Q706499)", "error");
    return;
  }

  setStatus("Fetching from Wikidata...", "info");
  currentQid = qid;

  try {
    const r = await fetch(`https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${qid}&props=claims|labels|descriptions&languages=en&format=json&origin=*`);
    const data = await r.json();
    const entity = data.entities[qid];

    if (!entity) {
      setStatus(`Item ${qid} not found`, "error");
      return;
    }

    const label = entity.labels?.en?.value || qid;
    const description = entity.descriptions?.en?.value || "";
    const claims = entity.claims || {};

    const result = generateWikitextFromClaims(qid, claims, label, description);
    currentWikitext = result.wikitext;

    $("#preview-wikitext").style.display = "block";
    $("#preview-wikitext").textContent = currentWikitext;
    $("#preview-count").textContent = `${result.fragmentCount} fragments from ${result.usedProps.length} properties (${result.usedProps.join(", ")})`;

    // Also populate the wikitext tab
    $("#wikitext").value = currentWikitext;
    $("#subject-qid").value = qid;

    setStatus(`Generated for ${label} (${qid})`, "success");
  } catch (e) {
    setStatus(`Error: ${e.message}`, "error");
  }
});

// Create article - full automation
$("#btn-inject").addEventListener("click", async () => {
  const wikitextSource = currentWikitext || $("#wikitext").value;
  const subjectQid = currentQid || $("#subject-qid").value.trim().toUpperCase();

  if (!wikitextSource) {
    setStatus("Generate or enter wikitext first", "error");
    return;
  }
  if (!subjectQid) {
    setStatus("Enter a subject QID", "error");
    return;
  }

  setStatus("Compiling wikitext...", "info");

  try {
    const clipboard = compileWikitext(wikitextSource, { subject: subjectQid });

    if (!clipboard.length) {
      setStatus("No fragments generated from wikitext", "error");
      return;
    }

    setStatus(`Creating article with ${clipboard.length} fragments...`, "info");

    // Send to background script to open new tab and run full automation
    chrome.runtime.sendMessage({
      action: "createArticle",
      qid: subjectQid,
      clipboard: clipboard,
    }, (response) => {
      if (response && response.started) {
        setStatus(`Opening editor for ${subjectQid}... Check the new tab!`, "success");
      } else {
        setStatus("Failed to start automation", "error");
      }
    });
  } catch (e) {
    setStatus(`Error: ${e.message}`, "error");
  }
});

// Auto-detect QID from current tab URL
(async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab.url && tab.url.includes("abstract.wikipedia.org")) {
      const match = tab.url.match(/\/(Q\d+)/);
      if (match) {
        $("#qid").value = match[1];
        $("#subject-qid").value = match[1];
        currentQid = match[1];
      }
    }
  } catch (e) { /* ignore */ }
})();
