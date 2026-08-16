import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const dist = resolve(root, 'dist');
const entry = resolve(dist, 'index.html');
const requiredFiles = [
  'index.html',
  'assets/index-aa1e555f.js',
  'assets/index-ByqX3rQm.css',
  'build-info.json',
];

for (const file of requiredFiles) {
  if (!existsSync(resolve(dist, file))) {
    throw new Error(`Build output is missing: ${file}`);
  }
}
const html = readFileSync(entry, 'utf8');
for (const reference of [
  '/assets/elmrkz_fsm/assets/index-aa1e555f.js',
  '/assets/elmrkz_fsm/assets/index-ByqX3rQm.css',
]) {
  if (!html.includes(reference)) {
    throw new Error(`Build entry is missing the required namespaced reference: ${reference}`);
  }
}
console.log('Recovered Dispatcher build integrity check passed.');
