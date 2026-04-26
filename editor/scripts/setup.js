#!/usr/bin/env node
// Install the Python dependencies the editor shells out to (Playwright,
// requests, python-dotenv, pyyaml) plus the Playwright browser binaries.
//
// Run from editor/ via `npm run setup`. Picks the same Python launcher the
// app picks at runtime — `py` on Windows, `python3` elsewhere — so a
// successful setup matches what the Electron main process will actually
// invoke.

const { spawnSync } = require('child_process');
const path = require('path');

const PYTHON = process.platform === 'win32' ? 'py' : 'python3';
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const REQUIREMENTS = path.join(REPO_ROOT, 'requirements.txt');

function run(args) {
  console.log(`> ${PYTHON} ${args.join(' ')}`);
  const r = spawnSync(PYTHON, args, { stdio: 'inherit' });
  if (r.error) {
    console.error(`Failed to spawn ${PYTHON}: ${r.error.message}`);
    console.error(`Install Python 3 and ensure '${PYTHON}' is on PATH, then re-run 'npm run setup'.`);
    process.exit(1);
  }
  if (r.status !== 0) process.exit(r.status || 1);
}

run(['-m', 'pip', 'install', '-r', REQUIREMENTS]);
run(['-m', 'playwright', 'install']);
console.log('Setup complete. You can now launch the editor with `npm start`.');
