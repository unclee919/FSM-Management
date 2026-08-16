import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = resolve(import.meta.dirname, '..');
const legacy = resolve(root, 'legacy');
const dist = resolve(root, 'dist');

const check = spawnSync(process.execPath, [resolve(root, 'scripts/verify-legacy.mjs')], {
  cwd: root,
  stdio: 'inherit',
});
if (check.status !== 0) process.exit(check.status ?? 1);

rmSync(dist, { recursive: true, force: true });
mkdirSync(resolve(dist, 'assets'), { recursive: true });
cpSync(resolve(legacy, 'assets'), resolve(dist, 'assets'), { recursive: true });

const entry = readFileSync(resolve(legacy, 'index.html'), 'utf8')
  .replace(/<script\s+src="\/__manus__\/debug-collector\.js"\s+defer><\/script>\s*/g, '');
writeFileSync(resolve(dist, 'index.html'), entry);
writeFileSync(resolve(dist, 'build-info.json'), `${JSON.stringify({
  artifact: 'recovered-legacy-dispatcher',
  assetBase: '/assets/elmrkz_fsm/',
  manifest: 'legacy-manifest.json',
}, null, 2)}\n`);
console.log('Built recovered Dispatcher artifacts into dist/.');
