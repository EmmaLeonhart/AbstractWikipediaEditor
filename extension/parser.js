// Wikitext parser - JS port of wikitext_parser.py
// Compiles wikitext templates into Abstract Wikipedia clipboard JSON

function z9s(zid) {
  return { "Z1K1": "Z9", "Z9K1": zid };
}

function z6(value) {
  return { "Z1K1": "Z6", "Z6K1": value };
}

function z6091(qid) {
  return { "Z1K1": z9s("Z6091"), "Z6091K1": z6(qid) };
}

function z18(argKey) {
  return { "Z1K1": z9s("Z18"), "Z18K1": z6(argKey) };
}

function z7call(funcId, argsDict) {
  const result = { "Z1K1": z9s("Z7"), "Z7K1": z9s(funcId) };
  Object.assign(result, argsDict);
  return result;
}

const IMPLICIT_REFS = {
  "$subject": "Z825K1",
  "$lang": "Z825K2",
};

function resolveValue(raw, variables) {
  raw = raw.trim();
  if (IMPLICIT_REFS[raw]) return z18(IMPLICIT_REFS[raw]);
  if (raw.startsWith("$")) {
    const varName = raw.slice(1);
    if (variables && variables[varName]) {
      return resolveValue(variables[varName], variables);
    }
    throw new Error(`Undefined variable: ${raw}`);
  }
  if (/^Q\d+$/.test(raw)) return z6091(raw);
  if (/^Z\d+$/.test(raw)) return z9s(raw);
  if (raw.toLowerCase() === "true" || raw.toLowerCase() === "yes") return z9s("Z41");
  if (raw.toLowerCase() === "false" || raw.toLowerCase() === "no") return z9s("Z42");
  return z6(raw);
}

function resolveFunctionName(name) {
  name = name.trim();
  if (/^Z\d+$/.test(name)) return name;
  return FUNCTION_ALIASES[name.toLowerCase()] || name;
}

function wrapAsFragment(funcId, funcCall, returnType) {
  if (returnType === "Z11") {
    return z7call("Z29749", {
      "Z29749K1": funcCall,
      "Z29749K2": z18("Z825K2"),
    });
  } else if (returnType === "Z6") {
    return z7call("Z27868", { "Z27868K1": funcCall });
  } else if (returnType === "Z89") {
    return funcCall;
  }
  return z7call("Z29749", {
    "Z29749K1": funcCall,
    "Z29749K2": z18("Z825K2"),
  });
}

function makeClipboardItem(value, index) {
  return {
    itemId: `Q8776414.${index + 1}#1`,
    originKey: `Q8776414.${index + 1}`,
    originSlotType: "Z89",
    value: value,
    objectType: "Z7",
    resolvingType: "Z89",
  };
}

function parseWikitext(text) {
  // Split frontmatter
  let body = text;
  const trimmed = text.trim();
  if (trimmed.startsWith("---")) {
    const parts = trimmed.split("---");
    if (parts.length >= 3) {
      body = parts.slice(2).join("---").trim();
    }
  }

  // Extract {{...}} calls
  const pattern = /\{\{(.+?)\}\}/gs;
  const calls = [];
  let match;
  while ((match = pattern.exec(body)) !== null) {
    const inner = match[1].trim();
    const parts = inner.split("|").map(p => p.trim());
    if (!parts.length) continue;
    const funcName = parts[0];
    const args = parts.slice(1);
    calls.push({ funcName, args });
  }
  return calls;
}

function compileWikitext(text, variables) {
  const calls = parseWikitext(text);
  const clipboard = [];

  for (const call of calls) {
    const funcId = resolveFunctionName(call.funcName);
    const funcInfo = FUNCTION_REGISTRY[funcId];

    const argsDict = {};
    if (funcInfo) {
      let argIdx = 0;
      for (let i = 0; i < funcInfo.params.length; i++) {
        const param = funcInfo.params[i];
        const fullKey = `${funcId}${param.key}`;

        if (param.type === "language") {
          argsDict[fullKey] = z18("Z825K2");
          continue;
        }

        if (argIdx < call.args.length) {
          argsDict[fullKey] = resolveValue(call.args[argIdx], variables);
          argIdx++;
        }
      }
    } else {
      // Unknown function: best effort
      for (let i = 0; i < call.args.length; i++) {
        argsDict[`${funcId}K${i + 1}`] = resolveValue(call.args[i], variables);
      }
    }

    const funcCall = z7call(funcId, argsDict);
    const returnType = funcInfo ? funcInfo.returns : "Z11";
    const wrapped = wrapAsFragment(funcId, funcCall, returnType);
    clipboard.push(makeClipboardItem(wrapped, clipboard.length));
  }

  return clipboard;
}

// Generate wikitext from a Wikidata item's claims
function generateWikitextFromClaims(qid, claims, label, description) {
  const p31Values = [];
  if (claims.P31) {
    for (const claim of claims.P31) {
      const v = extractQid(claim);
      if (v) p31Values.push(v);
    }
  }
  const p31Value = p31Values[0] || null;

  // Pick best location property (most specific wins)
  const locationPriority = ["P131", "P17", "P30"];
  let bestLocation = null;
  for (const pid of locationPriority) {
    if (pid in claims && pid in PROPERTY_MAPPING) { bestLocation = pid; break; }
  }

  const hasOccupation = "P106" in claims && "P106" in PROPERTY_MAPPING;

  const fragments = [];
  const usedProps = new Set();

  // P31 only if no location or occupation covers it
  if (p31Value && !bestLocation && !hasOccupation) {
    fragments.push(`{{is a | $subject | ${p31Value}}}`);
  }
  usedProps.add("P31");

  for (const [pid, pmap] of Object.entries(PROPERTY_MAPPING)) {
    if (usedProps.has(pid) || !(pid in claims)) continue;

    // Skip non-best location properties
    if (pmap.location_priority && pid !== bestLocation) continue;

    // Skip properties that conflict with others present
    if (pmap.skip_if && pmap.skip_if.some(other => other in claims)) continue;

    let value = null;
    for (const claim of claims[pid]) {
      const v = extractQid(claim);
      if (v) { value = v; break; }
    }
    if (!value) continue;

    let line = pmap.template.replace("$value", value);
    if (line.includes("$P31_value")) {
      if (p31Value) line = line.replace("$P31_value", p31Value);
      else continue;
    }
    fragments.push(line);
    usedProps.add(pid);
  }

  const lines = [
    "---",
    `title: ${label || qid}`,
    description ? `description: "${description}"` : "",
    `# Auto-generated from Wikidata ${qid}`,
    "variables: {}",
    "---",
    "",
    ...fragments,
  ].filter(l => l !== undefined);

  return { wikitext: lines.join("\n"), usedProps: [...usedProps], fragmentCount: fragments.length };
}

function extractQid(claim) {
  const snak = claim.mainsnak;
  if (!snak || snak.snaktype !== "value") return null;
  const dv = snak.datavalue;
  if (dv && dv.type === "wikibase-entityid") return dv.value.id;
  return null;
}
