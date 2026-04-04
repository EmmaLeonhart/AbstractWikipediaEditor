// Background service worker - coordinates the full article creation flow
// Receives messages from popup, opens tabs, and orchestrates content script

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "createArticle") {
    createArticle(message.qid, message.clipboard);
    sendResponse({ started: true });
  }
  return true;
});

async function createArticle(qid, clipboard) {
  // Open the edit page in a new tab
  const tab = await chrome.tabs.create({
    url: `https://abstract.wikipedia.org/w/index.php?title=${qid}&action=edit`,
    active: true,
  });

  // Wait for page to fully load, then run the automation
  chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
    if (tabId === tab.id && info.status === "complete") {
      chrome.tabs.onUpdated.removeListener(listener);
      // Give the editor extra time to initialize
      setTimeout(() => {
        chrome.tabs.sendMessage(tab.id, {
          action: "fullAutomation",
          clipboard: clipboard,
          qid: qid,
        });
      }, 5000);
    }
  });
}
