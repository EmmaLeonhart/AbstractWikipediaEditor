import { app, BrowserWindow, ipcMain, shell } from 'electron';
import * as path from 'path';
import * as https from 'https';
import * as fs from 'fs';
import * as os from 'os';
import { execFile } from 'child_process';

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.loadFile(path.join(__dirname, '..', 'index.html'));
  // win.webContents.openDevTools();
}

interface WikidataEntity {
  labels?: Record<string, { value: string }>;
  descriptions?: Record<string, { value: string }>;
  claims?: Record<string, WikidataClaim[]>;
}

interface WikidataClaim {
  mainsnak: {
    snaktype: string;
    datavalue?: {
      type: string;
      value: { id?: string };
    };
  };
}

interface ArticleResult {
  exists: boolean;
  content: string | null;
}

function fetchJSON<T>(url: string): Promise<T> {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'AbstractTestBot/1.0' } }, (res) => {
      let data = '';
      res.on('data', (chunk: string) => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

// Fetch Wikidata item labels, descriptions, and claims
ipcMain.handle('fetch-item', async (_event, qid: string): Promise<WikidataEntity | null> => {
  const url = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${qid}&props=claims|labels|descriptions&languages=en&format=json`;
  const data = await fetchJSON<{ entities: Record<string, WikidataEntity> }>(url);
  return data.entities?.[qid] || null;
});

// Fetch English label for a QID
ipcMain.handle('fetch-label', async (_event, qid: string): Promise<string> => {
  const url = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${qid}&props=labels&languages=en&format=json`;
  const data = await fetchJSON<{ entities: Record<string, WikidataEntity> }>(url);
  return data.entities?.[qid]?.labels?.en?.value || qid;
});

// Batch fetch labels for multiple QIDs
ipcMain.handle('fetch-labels', async (_event, qids: string[]): Promise<Record<string, string>> => {
  const batchSize = 50;
  const results: Record<string, string> = {};
  for (let i = 0; i < qids.length; i += batchSize) {
    const batch = qids.slice(i, i + batchSize);
    const url = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${batch.join('|')}&props=labels&languages=en&format=json`;
    const data = await fetchJSON<{ entities: Record<string, WikidataEntity> }>(url);
    for (const [id, entity] of Object.entries(data.entities || {})) {
      results[id] = entity?.labels?.en?.value || id;
    }
  }
  return results;
});

// Fetch revision history for a QID from Abstract Wikipedia
interface RevisionInfo {
  revid: number;
  parentid: number;
  user: string;
  timestamp: string;
  comment: string;
  size: number;
}

ipcMain.handle('fetch-revisions', async (_event, qid: string): Promise<RevisionInfo[]> => {
  const url = `https://abstract.wikipedia.org/w/api.php?action=query&titles=${qid}&prop=revisions&rvprop=ids|timestamp|user|comment|size&rvlimit=50&format=json`;
  try {
    const data = await fetchJSON<{ query?: { pages?: Record<string, { revisions?: RevisionInfo[] }> } }>(url);
    const pages = data.query?.pages || {};
    for (const page of Object.values(pages)) {
      if (page.revisions) return page.revisions;
    }
    return [];
  } catch (e) {
    console.error('[fetch-revisions]', e);
    return [];
  }
});

// Convert a specific revision to wikitext
ipcMain.handle('convert-article-revision', async (_event, qid: string, oldid: string): Promise<string> => {
  return await runPython('convert_article.py', [qid, '--oldid', oldid]);
});

// Check if article exists on Abstract Wikipedia
ipcMain.handle('check-article', async (_event, qid: string): Promise<ArticleResult> => {
  const url = `https://abstract.wikipedia.org/w/api.php?action=parse&page=${qid}&prop=wikitext&format=json`;
  try {
    console.log(`[check-article] Fetching ${url}`);
    const data = await fetchJSON<{ error?: unknown; parse?: { wikitext?: { '*'?: string } } }>(url);
    console.log(`[check-article] Response keys: ${Object.keys(data)}`);
    if (data.error) {
      console.log(`[check-article] API error:`, data.error);
      return { exists: false, content: null };
    }
    const wikitext = data.parse?.wikitext?.['*'] || null;
    console.log(`[check-article] Content length: ${wikitext?.length || 0}`);
    return { exists: !!wikitext, content: wikitext };
  } catch (e) {
    console.error(`[check-article] Exception:`, e);
    return { exists: false, content: null };
  }
});

const PYTHON = process.platform === 'win32' ? 'py' : 'python3';
const PROJECT_ROOT = path.join(__dirname, '..', '..');
const ENV_PATH = path.join(PROJECT_ROOT, '.env');

// --- Credentials (.env) management ---

ipcMain.handle('get-credentials', async (): Promise<{ username: string; password: string; mainPassword: string } | null> => {
  try {
    const text = fs.readFileSync(ENV_PATH, 'utf-8');
    const lines = text.split('\n');
    const vals: Record<string, string> = {};
    for (const line of lines) {
      const eq = line.indexOf('=');
      if (eq > 0) vals[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
    }
    return {
      username: vals['WIKI_USERNAME'] || '',
      password: vals['WIKI_PASSWORD'] || '',
      mainPassword: vals['WIKI_MAIN_PASSWORD'] || '',
    };
  } catch {
    return null;
  }
});

ipcMain.handle('save-credentials', async (_event, creds: { username: string; password: string; mainPassword: string }): Promise<boolean> => {
  try {
    const content = `WIKI_USERNAME=${creds.username}\nWIKI_PASSWORD=${creds.password}\nWIKI_MAIN_PASSWORD=${creds.mainPassword}\n`;
    fs.writeFileSync(ENV_PATH, content, 'utf-8');
    return true;
  } catch (e) {
    console.error('[save-credentials]', e);
    return false;
  }
});

function runPython(script: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    console.log(`[python] Running: ${script} ${args.join(' ')}`);
    console.log(`[python] CWD: ${PROJECT_ROOT}`);
    const child = execFile(PYTHON, [path.join(PROJECT_ROOT, script), ...args], {
      cwd: PROJECT_ROOT,
      env: { ...process.env },
      timeout: 300000, // 5 minutes for Playwright operations
      maxBuffer: 10 * 1024 * 1024,
    }, (err, stdout, stderr) => {
      if (stderr) console.log(`[python] stderr: ${stderr}`);
      if (stdout) console.log(`[python] stdout (last 500): ${stdout.slice(-500)}`);
      if (err) {
        console.error(`[python] Error:`, err.message);
        reject(new Error(stderr || err.message));
      } else {
        resolve(stdout);
      }
    });
  });
}

// Generate wikitext from Wikidata using our existing script
ipcMain.handle('generate-wikitext', async (_event, qid: string): Promise<string> => {
  const output = await runPython('generate_wikitext.py', [qid]);
  const lines = output.split('\n');
  const startIdx = lines.findIndex(l => l.startsWith('---'));
  if (startIdx >= 0) return lines.slice(startIdx).join('\n').trim();
  return output;
});

// Convert existing Abstract Wikipedia article to wikitext
ipcMain.handle('convert-article', async (_event, qid: string): Promise<string> => {
  return await runPython('convert_article.py', [qid]);
});

// Push to Abstract Wikipedia - uses editor wikitext directly
ipcMain.handle('push-article', async (_event, qid: string, wikitext: string, restoreRevId?: string): Promise<string> => {
  // Write editor wikitext to a temp file for the Python script
  const tmpFile = path.join(os.tmpdir(), `abstractbot_${qid}.wikitext`);
  fs.writeFileSync(tmpFile, wikitext, 'utf-8');
  console.log(`[push] Wrote wikitext to ${tmpFile}`);

  // Check if article already exists
  const r = await fetchJSON<Record<string, unknown>>(`https://abstract.wikipedia.org/w/api.php?action=parse&page=${qid}&prop=wikitext&format=json`);
  const exists = !r.error;
  const script = exists ? 'edit_from_qid.py' : 'create_from_qid.py';
  console.log(`[push] ${qid} ${exists ? 'exists, editing' : 'does not exist, creating'}`);

  const args = [qid, '--wikitext', tmpFile, '--apply', '--headed'];
  if (restoreRevId && script === 'edit_from_qid.py') {
    args.push('--restore-rev', restoreRevId);
  }

  try {
    return await runPython(script, args);
  } finally {
    try { fs.unlinkSync(tmpFile); } catch {}
  }
});

// Open external links in default browser
app.on('web-contents-created', (_event, contents) => {
  contents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  contents.on('will-navigate', (event, url) => {
    if (url.startsWith('https://www.wikidata.org')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
