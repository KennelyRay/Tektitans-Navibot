// Bundles the Navibot React/JSX frontend into a single static JS file.
//
// This is a pre-build step, not part of the Vercel deploy pipeline (that
// pipeline only builds api/index.py as a Python function). Run `npm run
// build` locally after editing anything in frontend/src, then commit the
// regenerated static/js/navibot.bundle.js along with your source changes.
import { build, context } from 'esbuild';
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

const watch = process.argv.includes('--watch');

const OUTFILE = 'static/js/navibot.bundle.js';
const MIRROR_OUTFILE = 'api/static/js/navibot.bundle.js';

const options = {
    entryPoints: ['frontend/src/main.jsx'],
    bundle: true,
    minify: !watch,
    sourcemap: watch,
    outfile: OUTFILE,
    jsx: 'automatic',
    target: ['es2019'],
    logLevel: 'info',
};

function syncMirror() {
    mkdirSync(dirname(MIRROR_OUTFILE), { recursive: true });
    copyFileSync(OUTFILE, MIRROR_OUTFILE);
    console.log(`Synced ${OUTFILE} -> ${MIRROR_OUTFILE}`);
}

if (watch) {
    const ctx = await context({
        ...options,
        plugins: [
            {
                name: 'sync-mirror',
                setup(build) {
                    build.onEnd(() => syncMirror());
                },
            },
        ],
    });
    await ctx.watch();
    console.log('Watching frontend/src for changes...');
} else {
    await build(options);
    syncMirror();
    console.log('Build complete.');
}
