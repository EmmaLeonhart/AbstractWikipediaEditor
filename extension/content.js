// Content script: runs on abstract.wikipedia.org pages
// Handles clipboard injection into the Abstract Wikipedia editor

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "injectClipboard") {
    try {
      const clipboard = message.clipboard;

      // Inject into localStorage
      localStorage.setItem("ext-wikilambda-app-clipboard", JSON.stringify(clipboard));

      // Try to inject into Vue/Pinia store directly
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

      sendResponse({
        success: true,
        message: `Injected ${clipboard.length} fragments into clipboard`,
      });
    } catch (e) {
      sendResponse({
        success: false,
        error: e.message,
      });
    }
  }
  return true; // Keep message channel open for async response
});
