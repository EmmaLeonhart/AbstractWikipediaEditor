import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('api', {
  fetchItem: (qid: string) => ipcRenderer.invoke('fetch-item', qid),
  fetchLabel: (qid: string) => ipcRenderer.invoke('fetch-label', qid),
  fetchLabels: (qids: string[]) => ipcRenderer.invoke('fetch-labels', qids),
  checkArticle: (qid: string) => ipcRenderer.invoke('check-article', qid),
  generateWikitext: (qid: string) => ipcRenderer.invoke('generate-wikitext', qid),
  convertArticle: (qid: string) => ipcRenderer.invoke('convert-article', qid),
  renderWikitext: (subject: string, lines: string[]) => ipcRenderer.invoke('render-wikitext', subject, lines),
  convertArticleRevision: (qid: string, oldid: string) => ipcRenderer.invoke('convert-article-revision', qid, oldid),
  fetchRevisions: (qid: string) => ipcRenderer.invoke('fetch-revisions', qid),
  pushArticle: (qid: string, wikitext: string, restoreRevId?: string, editSummary?: string) => ipcRenderer.invoke('push-article', qid, wikitext, restoreRevId, editSummary),
  getCredentials: () => ipcRenderer.invoke('get-credentials'),
  saveCredentials: (creds: { username: string; mainPassword: string }) => ipcRenderer.invoke('save-credentials', creds),
  checkLegacyCredentials: () => ipcRenderer.invoke('check-legacy-credentials'),
  migrateCredentials: () => ipcRenderer.invoke('migrate-credentials'),
});
