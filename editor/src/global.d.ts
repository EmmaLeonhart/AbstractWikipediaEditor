interface RevisionInfo {
  revid: number;
  parentid: number;
  user: string;
  timestamp: string;
  comment: string;
  size: number;
}

interface ElectronAPI {
  fetchItem: (qid: string) => Promise<unknown>;
  fetchLabel: (qid: string) => Promise<string>;
  fetchLabels: (qids: string[]) => Promise<Record<string, string>>;
  checkArticle: (qid: string) => Promise<{ exists: boolean; content: string | null }>;
  generateWikitext: (qid: string) => Promise<string>;
  convertArticle: (qid: string) => Promise<string>;
  convertArticleRevision: (qid: string, oldid: string) => Promise<string>;
  fetchRevisions: (qid: string) => Promise<RevisionInfo[]>;
  pushArticle: (qid: string, wikitext: string, restoreRevId?: string) => Promise<string>;
  getCredentials: () => Promise<{ username: string; password: string; mainPassword: string } | null>;
  saveCredentials: (creds: { username: string; password: string; mainPassword: string }) => Promise<boolean>;
}

interface Window {
  api: ElectronAPI;
}
