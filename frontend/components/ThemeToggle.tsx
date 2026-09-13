"use client";

import { useEffect, useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import clsx from "clsx";

type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "finmate_theme";

/**
 * Inlined in <head> so the correct theme is on <html> before first paint.
 * Without this the page renders light, then flips — a visible flash on every
 * load for dark-mode users.
 */
export const themeScript = `(function(){try{
var t=localStorage.getItem("${STORAGE_KEY}")||"system";
var d=t==="dark"||(t==="system"&&window.matchMedia("(prefers-color-scheme: dark)").matches);
document.documentElement.setAttribute("data-theme",d?"dark":"light");
}catch(e){}})();`;

function resolve(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(theme: Theme) {
  const root = document.documentElement;
  // Transitions are enabled only for the duration of the swap, so normal
  // interaction isn't slowed by a global colour transition.
  root.classList.add("theme-switching");
  root.setAttribute("data-theme", resolve(theme));
  window.setTimeout(() => root.classList.remove("theme-switching"), 220);
}

const OPTIONS: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "system", icon: Monitor, label: "System" },
  { value: "dark", icon: Moon, label: "Dark" },
];

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [theme, setTheme] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = (localStorage.getItem(STORAGE_KEY) as Theme) || "system";
    setTheme(stored);
  }, []);

  // Follow the OS while on "system".
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  function choose(next: Theme) {
    setTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode: the choice just won't persist */
    }
    apply(next);
  }

  // Render the shell before mount so layout doesn't shift; the active state
  // fills in once localStorage is readable.
  if (compact) {
    const isDark = mounted ? resolve(theme) === "dark" : true;
    return (
      <button
        onClick={() => choose(isDark ? "light" : "dark")}
        aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        className="p-2 rounded-lg text-mist hover:text-white hover:bg-white/[0.06] transition-colors"
      >
        {isDark ? <Sun size={16} /> : <Moon size={16} />}
      </button>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex items-center gap-0.5 p-0.5 rounded-lg border border-line bg-white/[0.03]"
    >
      {OPTIONS.map(({ value, icon: Icon, label }) => {
        const active = mounted && theme === value;
        return (
          <button
            key={value}
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => choose(value)}
            className={clsx(
              "p-1.5 rounded-md transition-colors",
              active
                ? "bg-mint/15 text-mint"
                : "text-mist hover:text-white hover:bg-white/[0.05]"
            )}
          >
            <Icon size={14} />
          </button>
        );
      })}
    </div>
  );
}
