/**
 * Verification build that cannot disturb a running dev server.
 *
 * `next build` writes into distDir, which defaults to the same .next the dev
 * server reads from. Building while dev is running deletes chunks out from
 * under it, leaving the dev server throwing ENOENT on /_next/static and
 * "__webpack_modules__[moduleId] is not a function" until it is restarted.
 *
 * Usage: npm run build:check
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// Resolve Next's JS entry and run it with this Node binary. Spawning the
// `next`/`npx` shim instead fails with EINVAL on Windows, where Node 20 will
// not launch a .cmd without a shell - and going through a shell would then
// need its own quoting.
const nextBin = require.resolve("next/dist/bin/next");

const child = spawn(process.execPath, [nextBin, "build"], {
  stdio: "inherit",
  env: { ...process.env, NEXT_DIST_DIR: ".next-check" },
});

child.on("exit", (code) => process.exit(code ?? 1));
child.on("error", (err) => {
  console.error("build:check could not start next build:", err.message);
  process.exit(1);
});
