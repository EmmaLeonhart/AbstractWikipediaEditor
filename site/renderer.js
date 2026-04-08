// Renderer for Abstract Wikipedia wikitext templates
// Ported from editor/src/renderer.ts - same logic used in the Electron app

const ALIASES = {
  'location': 'Z26570', 'located in': 'Z26570',
  'is a': 'Z26039', 'instance of': 'Z26039',
  'kind of': 'Z26095', 'subclass of': 'Z26095',
  'role': 'Z28016', 'is the x of': 'Z28016',
  'describe': 'Z29591', 'adjective class': 'Z29591',
  'class of class': 'Z27173',
  'class with adj': 'Z29743',
  'superlative': 'Z27243',
  'spo': 'Z26955',
  'are': 'Z26627', 'plural class': 'Z26627',
  'album': 'Z28803',
  'sunset': 'Z30000',
  'begins': 'Z31405',
  'auto article': 'Z29822',
  'comparative measurement': 'Z32229',
};

const REVERSE_ALIASES = {};
for (const [alias, zid] of Object.entries(ALIASES)) {
  if (!REVERSE_ALIASES[zid]) REVERSE_ALIASES[zid] = alias;
}

const labelCache = {};

function parseTemplates(text) {
  const fragments = [];
  const pattern = /\{\{(.+?)\}\}/gs;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const parts = match[1].trim().split('|').map(s => s.trim());
    if (parts.length === 0) continue;
    const funcId = ALIASES[parts[0].toLowerCase()] || parts[0];
    fragments.push({ funcId, args: parts.slice(1) });
  }
  return fragments;
}

function qLink(qid) {
  const label = labelCache[qid] || qid;
  return `<a href="https://www.wikidata.org/wiki/${qid}" title="${qid}">${label}</a>`;
}

function resolveArg(a, subjectQid) {
  if (a === 'SUBJECT') return qLink(subjectQid);
  if (a === '$lang') return '<em>language</em>';
  if (/^Q\d+$/.test(a)) return qLink(a);
  return a;
}

function formatNumber(raw) {
  if (!raw) return '?';
  if (raw.includes('/')) {
    const [n, d] = raw.split('/');
    return n.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '/' +
           d.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  return raw.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function renderSentence(frag, subjectQid) {
  const a = frag.args.map(arg => resolveArg(arg, subjectQid));
  switch (frag.funcId) {
    case 'Z26570': return `${a[0]} is a ${a[1]} in ${a[2]}.`;
    case 'Z26039': return `${a[0]} is a ${a[1]}.`;
    case 'Z26095': return `A ${a[0]} is a ${a[1]}.`;
    case 'Z28016': return `${a[0]} is the ${a[1]} of ${a[2]}.`;
    case 'Z26955': return `${a[1]} is ${a[0]} of ${a[2]}.`;
    case 'Z29591': return `${a[0]} is a ${a[1]} ${a[2]}.`;
    case 'Z26627': return `${a[0]} are ${a[1]}.`;
    case 'Z27243': return `${a[0]} is the ${a[1]} ${a[2]} in ${a[3]}.`;
    case 'Z27173': return `${a[0]} is ${a[1]} ${a[2]}.`;
    case 'Z29743': return `A ${a[0]} is a ${a[1]} ${a[2]}.`;
    case 'Z32229': return `${a[0]} has a ${a[2]} ${formatNumber(a[3])} times that of ${a[1]}.`;
    default: return a.join(' ');
  }
}

async function fetchLabels(qids) {
  const missing = qids.filter(q => !labelCache[q]);
  if (missing.length === 0) return;

  for (let i = 0; i < missing.length; i += 50) {
    const batch = missing.slice(i, i + 50);
    try {
      const r = await fetch(
        `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${batch.join('|')}&props=labels&languages=en&format=json&origin=*`
      );
      const data = await r.json();
      for (const [id, entity] of Object.entries(data.entities || {})) {
        labelCache[id] = entity?.labels?.en?.value || id;
      }
    } catch (e) {
      for (const q of batch) labelCache[q] = q;
    }
  }
}

async function renderWikitext(wikitext, subjectQid, targetEl) {
  // Split by blank lines into paragraph groups.
  // Lines within a group (separated by single newlines) form one paragraph.
  const paragraphs = wikitext.split(/\n\s*\n/).filter(p => p.trim());
  const paragraphFragments = paragraphs.map(p => parseTemplates(p));
  const allFragments = paragraphFragments.flat();

  if (allFragments.length === 0) {
    targetEl.innerHTML = '<em>No fragments to render.</em>';
    return;
  }

  // Collect all QIDs that need labels
  const needed = new Set();
  if (subjectQid) needed.add(subjectQid);
  for (const frag of allFragments) {
    for (const arg of frag.args) {
      if (/^Q\d+$/.test(arg)) needed.add(arg);
    }
  }

  targetEl.innerHTML = '<em>Resolving labels...</em>';
  await fetchLabels([...needed]);

  // Render each paragraph group: sentences joined with spaces inside a <p>
  targetEl.innerHTML = paragraphFragments
    .filter(frags => frags.length > 0)
    .map(frags => {
      const sentences = frags.map(f => renderSentence(f, subjectQid)).join(' ');
      return `<p>${sentences}</p>`;
    }).join('');
}
