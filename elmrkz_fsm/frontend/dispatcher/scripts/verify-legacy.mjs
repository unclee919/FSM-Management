import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const legacy = resolve(root, 'legacy');
const entry = resolve(legacy, 'index.html');
const expectedAssets = [
  'assets/index-aa1e555f.js',
  'assets/index-ByqX3rQm.css',
];

if (!existsSync(entry)) {
  throw new Error('Recovered legacy entry is missing: legacy/index.html');
}
const html = readFileSync(entry, 'utf8');
for (const asset of expectedAssets) {
  if (!existsSync(resolve(legacy, asset))) {
    throw new Error(`Recovered legacy asset is missing: ${asset}`);
  }
  if (!html.includes(`/assets/elmrkz_fsm/${asset}`)) {
    throw new Error(`Entry does not use the required namespaced asset path: ${asset}`);
  }
}
if (!/<meta\s+name="viewport"/i.test(html)) {
  throw new Error('Recovered entry is missing its responsive viewport declaration.');
}

const files = ['index.html', ...expectedAssets];
const manifest = Object.fromEntries(files.map((file) => [
  file,
  createHash('sha256').update(readFileSync(resolve(legacy, file))).digest('hex'),
]));
writeFileSync(resolve(root, 'legacy-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Validated ${files.length} recovered Dispatcher artifacts.`);
