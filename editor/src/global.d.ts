interface RevisionInfo {
  revid: number;
  parentid: number;
  user: string;
  timestamp: string;
  comment: string;
  size: number;
}

interface RenderLineResult {
  html: string | null;
  error: string | null;
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
  pushArticle: (qid: string, wikitext: string, restoreRevId?: string, editSummary?: string) => Promise<string>;
  renderWikitext: (subject: string, lines: string[]) => Promise<RenderLineResult[]>;
  getCredentials: () => Promise<{ username: string; mainPassword: string } | null>;
  saveCredentials: (creds: { username: string; mainPassword: string }) => Promise<boolean>;
  checkLegacyCredentials: () => Promise<boolean>;
  migrateCredentials: () => Promise<boolean>;
}

interface Window {
  api: ElectronAPI;
}
