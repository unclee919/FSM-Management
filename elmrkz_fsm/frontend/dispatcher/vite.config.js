import { defineConfig } from 'vite';

// The recovered legacy build is copied deterministically by scripts/build-legacy.mjs.
// This configuration is the approved base for the incremental React/Vite rewrite.
export default defineConfig({
  base: '/assets/elmrkz_fsm/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true,
  },
});
