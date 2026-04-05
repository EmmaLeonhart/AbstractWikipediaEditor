interface ElectronAPI {
  fetchItem: (qid: string) => Promise<unknown>;
  fetchLabel: (qid: string) => Promise<string>;
  fetchLabels: (qids: string[]) => Promise<Record<string, string>>;
  checkArticle: (qid: string) => Promise<{ exists: boolean; content: string | null }>;
  generateWikitext: (qid: string) => Promise<string>;
  convertArticle: (qid: string) => Promise<string>;
  pushArticle: (qid: string, wikitext: string) => Promise<string>;
  getCredentials: () => Promise<{ username: string; password: string; mainPassword: string } | null>;
  saveCredentials: (creds: { username: string; password: string; mainPassword: string }) => Promise<boolean>;
}

interface Window {
  api: ElectronAPI;
}
