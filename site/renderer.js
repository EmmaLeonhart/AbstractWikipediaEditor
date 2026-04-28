// Renderer for Abstract Wikipedia wikitext templates
// Ported from editor/src/renderer.ts - same logic used in the Electron app

const ALIASES = {
  'location': 'Z26570', 'located in': 'Z26570',
  'is a': 'Z26039', 'instance of': 'Z26039',
  'kind of': 'Z26039', 'subclass of': 'Z26039',
  'role': 'Z28016', 'is the x of': 'Z28016',
  'describe': 'Z29591', 'adjective class': 'Z29591',
  'class of class': 'Z27173',
  'class with adj': 'Z29743',
  'superlative': 'Z27243',
  'spo': 'Z28016',
  'minor role': 'Z32982', 'non-defining role': 'Z32982',
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

// Infix-form predicate map. Mirrors INFIX_PREDICATES in wikitext_parser.py
// and editor/src/renderer.ts. {{infix|X|predicate|Y}} rewrites to
// {{target_zid|X|role_qid|Y}}.
const INFIX_PREDICATES = {
  'part of': ['Z32982', 'Q66305721'],
};

function applyInfixRewrite(parts) {
  if (parts.length < 4 || parts[0].toLowerCase() !== 'infix') return parts;
  const mapping = INFIX_PREDICATES[parts[2].toLowerCase()];
  if (!mapping) return parts;
  const [targetZid, roleQid] = mapping;
  return [targetZid, parts[1], roleQid, parts[3], ...parts.slice(4)];
}

const labelCache = {};

function parseTemplates(text) {
  const fragments = [];
  const pattern = /\{\{(.+?)\}\}/gs;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const parts = applyInfixRewrite(match[1].trim().split('|').map(s => s.trim()));
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
  if (a === 'SUBJECT' || a === 'it') return qLink(subjectQid);
  if (a === '$lang') return '<em>language</em>';
  if (/^Q\d+$/.test(a)) return qLink(a);
  return a;
}

// Plain-text label used to pick "a" vs "an" in renderSentence. resolveArg
// returns HTML, which we can't read the first letter off, so we look up
// the underlying label (or use the raw arg if it isn't a QID).
function rawArg(a, subjectQid) {
  if (a === 'SUBJECT' || a === 'it') return labelCache[subjectQid] || subjectQid;
  if (a === '$lang') return 'language';
  if (/^Q\d+$/.test(a)) return labelCache[a] || a;
  return a;
}

function articleFor(label) {
  const first = (label || '').trim().charAt(0).toLowerCase();
  return 'aeiou'.includes(first) ? 'an' : 'a';
}

function cap(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
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
  const r = frag.args.map(arg => rawArg(arg, subjectQid));
  switch (frag.funcId) {
    case 'Z26570': return `${a[0]} is ${articleFor(r[1])} ${a[1]} in ${a[2]}.`;
    case 'Z26039': return `${a[0]} is ${articleFor(r[1])} ${a[1]}.`;
    case 'Z26095': return `${cap(articleFor(r[0]))} ${a[0]} is ${articleFor(r[1])} ${a[1]}.`;
    case 'Z28016': return `${a[0]} is the ${a[1]} of ${a[2]}.`;
    case 'Z32982': return `${a[0]} is ${articleFor(r[1])} ${a[1]} in ${a[2]}.`;
    case 'Z29591': return `${a[0]} is ${articleFor(r[1])} ${a[1]} ${a[2]}.`;
    case 'Z26627': return `${a[0]} are ${a[1]}.`;
    case 'Z27243': return `${a[0]} is the ${a[1]} ${a[2]} in ${a[3]}.`;
    case 'Z27173': return `${a[0]} is ${a[1]} ${a[2]}.`;
    case 'Z29743': return `${cap(articleFor(r[0]))} ${a[0]} is ${articleFor(r[1])} ${a[1]} ${a[2]}.`;
    case 'Z32229': return `${a[0]} has ${articleFor(r[2])} ${a[2]} ${formatNumber(a[3])} times that of ${a[1]}.`;
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
  // Multiple {{...}} calls between paragraph breaks bundle into one
  // paragraph. Paragraph breaks are blank lines or {{p}} markers.
  // ==QID== section headers also break paragraphs and emit a header.
  const splitRe = /(\{\{\s*p\s*\}\}|^==\s*(.+?)\s*==$|\n[ \t]*\n)/gim;

  const items = [];
  let sectionCounter = 0;
  let lastEnd = 0;
  let m;

  function pushParagraph(text) {
    const frags = parseTemplates(text);
    if (frags.length === 0) return;
    items.push({ type: 'paragraph', fragments: frags });
  }

  while ((m = splitRe.exec(wikitext)) !== null) {
    const segment = wikitext.slice(lastEnd, m.index);
    if (segment.trim()) pushParagraph(segment);

    const headerText = m[2];
    if (headerText !== undefined) {
      if (/^Q\d+$/.test(headerText)) {
        items.push({ type: 'header', qid: headerText, label: null });
      } else {
        sectionCounter++;
        items.push({ type: 'header', qid: 'Q' + (198 + sectionCounter), label: String(sectionCounter) + ' (' + headerText + ')' });
      }
    }
    lastEnd = m.index + m[0].length;
  }
  const tail = wikitext.slice(lastEnd);
  if (tail.trim()) pushParagraph(tail);

  if (items.length === 0) {
    targetEl.innerHTML = '<em>No fragments to render.</em>';
    return;
  }

  // Collect all QIDs that need labels
  const needed = new Set();
  if (subjectQid) needed.add(subjectQid);
  for (const item of items) {
    if (item.type === 'header' && !item.label) {
      needed.add(item.qid);
    } else if (item.type === 'paragraph') {
      for (const frag of item.fragments) {
        for (const arg of frag.args) {
          if (/^Q\d+$/.test(arg)) needed.add(arg);
        }
      }
    }
  }

  targetEl.innerHTML = '<em>Resolving labels...</em>';
  await fetchLabels([...needed]);

  // Render items
  targetEl.innerHTML = items.map(item => {
    if (item.type === 'header') {
      const display = item.label || labelCache[item.qid] || item.qid;
      return `<h2>${display}</h2>`;
    }
    const sentences = item.fragments.map(f => renderSentence(f, subjectQid)).join(' ');
    return `<p>${sentences}</p>`;
  }).join('');
}
