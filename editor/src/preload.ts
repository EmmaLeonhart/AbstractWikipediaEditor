import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('api', {
  fetchItem: (qid: string) => ipcRenderer.invoke('fetch-item', qid),
  fetchLabel: (qid: string) => ipcRenderer.invoke('fetch-label', qid),
  fetchLabels: (qids: string[]) => ipcRenderer.invoke('fetch-labels', qids),
  checkArticle: (qid: string) => ipcRenderer.invoke('check-article', qid),
  generateWikitext: (qid: string) => ipcRenderer.invoke('generate-wikitext', qid),
  convertArticle: (qid: string) => ipcRenderer.invoke('convert-article', qid),
  pushArticle: (qid: string, wikitext: string) => ipcRenderer.invoke('push-article', qid, wikitext),
});
