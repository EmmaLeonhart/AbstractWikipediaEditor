interface ElectronAPI {
  fetchItem: (qid: string) => Promise<unknown>;
  fetchLabel: (qid: string) => Promise<string>;
  fetchLabels: (qids: string[]) => Promise<Record<string, string>>;
  checkArticle: (qid: string) => Promise<{ exists: boolean; content: string | null }>;
  generateWikitext: (qid: string) => Promise<string>;
  convertArticle: (qid: string) => Promise<string>;
  pushArticle: (qid: string, wikitext: string) => Promise<string>;
}

interface Window {
  api: ElectronAPI;
}
