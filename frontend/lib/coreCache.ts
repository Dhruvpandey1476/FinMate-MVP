"use client";

import type { CoreLoop } from "./types";

/**
 * Per-tab cache of the last successfully loaded Core Loop.
 *
 * Every Core Loop section is conditional on its data, so any remount drops the
 * dashboard back to its pre-data layout - which looks identical to the old
 * design and reads as "the update reverted". Restoring the last good payload on
 * mount means a remount repaints the full hero immediately and then revalidates
 * in the background, instead of visibly regressing.
 *
 * sessionStorage, not localStorage: this is the user's financial position, so
 * it should not outlive the tab. Entries are stamped with the build SHA so a
 * new deployment never restores a payload shaped for older code.
 */
const KEY = "finmate_core_loop";
const MAX_AGE_MS = 10 * 60 * 1000;

interface Entry {
  sha: string;
  at: number;
  data: CoreLoop;
}

const buildSha = () => process.env.NEXT_PUBLIC_BUILD_SHA ?? "dev";

export function readCoreCache(): CoreLoop | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;

    const entry = JSON.parse(raw) as Entry;
    // A payload written by a different build may not match the current shape.
    if (entry.sha !== buildSha()) return null;
    if (Date.now() - entry.at > MAX_AGE_MS) return null;
    return entry.data ?? null;
  } catch {
    // Private mode, quota, or corrupt JSON - fall through to a normal fetch.
    return null;
  }
}

export function writeCoreCache(data: CoreLoop): void {
  if (typeof window === "undefined") return;
  try {
    const entry: Entry = { sha: buildSha(), at: Date.now(), data };
    sessionStorage.setItem(KEY, JSON.stringify(entry));
  } catch {
    /* caching is an optimisation; never let it break a render */
  }
}

export function clearCoreCache(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
