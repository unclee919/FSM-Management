# Elmrkz FSM Dispatcher — Recovered Build Project

## Purpose

The original Vite/React source was not present on the staging host and no source map or frontend archive was recoverable. This project places the **currently verified live Dispatcher bundle** under source control as a legacy artifact, gives it deterministic integrity checks, and provides a reproducible build artifact for Frappe.

> The `legacy/` directory is a versioned recovery artifact, not maintainable application source. Do not hand-edit its bundled JavaScript. Any product enhancement should be implemented in a new, tested Vite/React source layer and migrated incrementally.

## Commands

```bash
pnpm install --frozen-lockfile
pnpm run check
pnpm run build
pnpm run verify-build
```

The build writes the Frappe-served Dispatcher files to `dist/` using the asset namespace configured in `vite.config.js`:

```text
/assets/elmrkz_fsm/
```

## Deployment contract

The deployment process must copy the contents of `dist/` to the custom app’s public directory:

```text
apps/elmrkz_fsm/elmrkz_fsm/public/
```

After copying the build, run the standard Frappe cache clear. The native `FSM Dispatcher` page must continue to load the versioned iframe entry through `/assets/elmrkz_fsm/index.html`.

## Incremental recovery plan

1. Keep `legacy/` unchanged as a tested fallback and verify `legacy-manifest.json` in every build.
2. Create maintainable React components under `src/` for one low-risk surface at a time.
3. Use the Vite configuration’s `/assets/elmrkz_fsm/` base path from the beginning.
4. Add browser regression tests for the Dispatcher’s Grid, Gantt, Map, Calendar, filtering, selection, and Frappe deep-link actions before replacing the legacy artifact.
5. Remove the legacy artifact only after functional and visual parity are signed off in staging.
