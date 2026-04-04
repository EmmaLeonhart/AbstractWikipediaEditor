// Content script: runs on abstract.wikipedia.org pages
// Handles the full automated flow: inject clipboard, paste fragments, publish

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "injectClipboard") {
    // Simple injection only (legacy)
    try {
      injectClipboard(message.clipboard);
      sendResponse({ success: true });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
  }

  if (message.action === "fullAutomation") {
    // Full flow: inject, paste all fragments, publish
    runFullAutomation(message.clipboard, message.qid);
    sendResponse({ success: true });
  }

  return true;
});

function injectClipboard(clipboard) {
  localStorage.setItem("ext-wikilambda-app-clipboard", JSON.stringify(clipboard));
  const app = document.querySelector(".ext-wikilambda-app")?.__vue_app__
    || document.querySelector("#ext-wikilambda-app")?.__vue_app__;
  if (app) {
    const pinia = app.config.globalProperties.$pinia;
    if (pinia) {
      const store = pinia._s.get("main");
      if (store) {
        store.clipboardItems = clipboard;
      }
    }
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function click(el) {
  if (el) {
    el.scrollIntoView({ block: "center" });
    el.click();
  }
}

async function runFullAutomation(clipboard, qid) {
  try {
    updateStatus("Injecting clipboard...");
    injectClipboard(clipboard);
    await sleep(1000);

    // Paste each fragment
    for (let i = 0; i < clipboard.length; i++) {
      updateStatus(`Pasting fragment ${i + 1}/${clipboard.length}...`);

      // Click "add fragment" menu
      const addBtn = document.querySelector("button[aria-label='Menu for selecting and adding a new fragment']");
      if (!addBtn) { updateStatus("ERROR: Can't find add fragment button"); return; }
      click(addBtn);
      await sleep(1000);

      // Click "Add empty fragment"
      const options = document.querySelectorAll("[role='option']");
      let addEmpty = null;
      for (const opt of options) {
        if (opt.textContent.includes("Add empty fragment")) {
          addEmpty = opt;
          break;
        }
      }
      if (!addEmpty) { updateStatus("ERROR: Can't find 'Add empty fragment'"); return; }
      click(addEmpty);
      await sleep(2000);

      // Click the dots menu on the correct fragment
      const dots = document.querySelectorAll("button[aria-label*='fragment-actions-menu']");
      const targetDot = i === 0 ? dots[0] : dots[dots.length - 1];
      if (!targetDot) { updateStatus("ERROR: Can't find fragment dots menu"); return; }
      click(targetDot);
      await sleep(1000);

      // Click "Paste from clipboard"
      const allOptions = document.querySelectorAll("[role='option']");
      let pasteOpt = null;
      for (const opt of allOptions) {
        if (opt.textContent.includes("Paste from clipboard")) {
          pasteOpt = opt;
          break;
        }
      }
      if (!pasteOpt) { updateStatus("ERROR: Can't find 'Paste from clipboard'"); return; }
      click(pasteOpt);
      await sleep(2000);

      // Click the correct clipboard item in the dialog
      const dialog = document.querySelector(".cdx-dialog");
      if (!dialog) { updateStatus("ERROR: No clipboard dialog"); return; }
      const items = dialog.querySelectorAll("div.ext-wikilambda-app-clipboard__item-head");
      if (items.length <= i) {
        updateStatus(`ERROR: Need clipboard item ${i} but only ${items.length} available`);
        return;
      }
      click(items[i]);
      await sleep(3000);
    }

    // Dismiss any lingering dialogs
    document.querySelectorAll(".cdx-dialog-backdrop").forEach(b => b.remove());
    document.querySelectorAll('.cdx-dialog button[aria-label="Close dialog"]').forEach(b => b.click());
    await sleep(2000);

    // Publish
    updateStatus("Publishing...");
    const pubBtn = document.querySelector("button.ext-wikilambda-app-abstract-publish__publish");
    if (pubBtn) {
      pubBtn.removeAttribute("disabled");
      pubBtn.disabled = false;
      await sleep(500);
      pubBtn.click();
      await sleep(4000);

      // Confirm dialog if present
      const dialogs = document.querySelectorAll(".cdx-dialog");
      for (const d of dialogs) {
        if (d.offsetParent !== null) {
          const btns = d.querySelectorAll("button.cdx-button--action-progressive");
          for (const b of btns) {
            if (b.offsetParent !== null && !b.disabled) {
              b.click();
              break;
            }
          }
        }
      }
      await sleep(15000);

      // Navigate to the created page
      window.location.href = `https://abstract.wikipedia.org/wiki/${qid}`;
    } else {
      updateStatus("ERROR: Can't find publish button");
    }
  } catch (e) {
    updateStatus(`ERROR: ${e.message}`);
  }
}

function updateStatus(msg) {
  console.log(`[AbstractBot] ${msg}`);
  // Also show a visual indicator on the page
  let indicator = document.getElementById("abstractbot-status");
  if (!indicator) {
    indicator = document.createElement("div");
    indicator.id = "abstractbot-status";
    indicator.style.cssText = "position:fixed;top:10px;right:10px;background:#3366cc;color:white;padding:10px 16px;border-radius:8px;font-size:14px;z-index:99999;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.3);";
    document.body.appendChild(indicator);
  }
  indicator.textContent = msg;
  if (msg.startsWith("ERROR")) {
    indicator.style.background = "#d33";
  }
}
