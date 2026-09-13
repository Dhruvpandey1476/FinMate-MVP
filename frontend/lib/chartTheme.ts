"use client";

import { useEffect, useState } from "react";

/**
 * Chart colours read from the live CSS theme tokens.
 *
 * Recharts needs concrete colour strings, so it can't use Tailwind classes.
 * Hardcoding hex meant grid lines tuned for a near-black page rendered almost
 * invisible on a white one. This resolves the same variables the rest of the
 * UI uses and re-reads them when the theme changes.
 */
export interface ChartTheme {
  mint: string;
  violet: string;
  gold: string;
  rose: string;
  grid: string;
  axis: string;
  tooltipBg: string;
  tooltipBorder: string;
  text: string;
}

const VARS: Record<keyof ChartTheme, string> = {
  mint: "--c-mint",
  violet: "--c-violet",
  gold: "--c-gold",
  rose: "--c-rose",
  grid: "--c-line",
  axis: "--c-mist",
  tooltipBg: "--c-panel",
  tooltipBorder: "--c-line",
  text: "--c-fg",
};

// Dark-theme values, used for the server render and as a fallback.
const FALLBACK: ChartTheme = {
  mint: "rgb(39 224 166)",
  violet: "rgb(139 124 255)",
  gold: "rgb(240 184 96)",
  rose: "rgb(255 107 122)",
  grid: "rgb(30 39 64)",
  axis: "rgb(94 106 135)",
  tooltipBg: "rgb(17 23 42)",
  tooltipBorder: "rgb(30 39 64)",
  text: "rgb(232 236 246)",
};

function read(): ChartTheme {
  if (typeof window === "undefined") return FALLBACK;
  const style = getComputedStyle(document.documentElement);
  const out = {} as ChartTheme;
  for (const key of Object.keys(VARS) as (keyof ChartTheme)[]) {
    const triple = style.getPropertyValue(VARS[key]).trim();
    out[key] = triple ? `rgb(${triple})` : FALLBACK[key];
  }
  return out;
}

export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(FALLBACK);

  useEffect(() => {
    setTheme(read());
    // ThemeToggle flips data-theme on <html>; re-read when it does.
    const observer = new MutationObserver(() => setTheme(read()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return theme;
}

/** Shared Recharts <Tooltip> styling. */
export function tooltipStyle(t: ChartTheme) {
  return {
    background: t.tooltipBg,
    border: `1px solid ${t.tooltipBorder}`,
    borderRadius: 12,
    fontSize: 12,
    color: t.text,
    boxShadow: "var(--shadow-lift)",
  };
}
