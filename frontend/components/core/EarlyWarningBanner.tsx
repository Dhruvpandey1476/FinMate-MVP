"use client";

/**
 * Early Warning banner.
 *
 * Tone is a nudge, not an error. A banner that shouts gets dismissed, and a
 * dismissed channel warns nobody - so severity is carried by a small colour
 * accent rather than a full red alert, and every warning can be waved away.
 *
 * Dismissals persist per warning key in localStorage. The keys are stable
 * across recomputes (see agents/early_warning.py), so waving away "Food is
 * running hot" this week does not silence it next month.
 */
import { useEffect, useState } from "react";
import { AlertTriangle, Info, X, ChevronRight } from "lucide-react";
import { GlassCard } from "@/components/GlassCard";
import { formatINR } from "@/lib/api";
import type { EarlyWarning } from "@/lib/types";

const DISMISSED_KEY = "finmate_dismissed_warnings";

const STYLES: Record<string, { ring: string; text: string; Icon: typeof Info }> = {
  critical: { ring: "border-rose/40", text: "text-rose", Icon: AlertTriangle },
  warn: { ring: "border-gold/40", text: "text-gold", Icon: AlertTriangle },
  info: { ring: "border-line", text: "text-mint", Icon: Info },
};

function loadDismissed(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(DISMISSED_KEY) || "[]");
  } catch {
    return [];
  }
}

export default function EarlyWarningBanner({ warnings }: { warnings: EarlyWarning[] }) {
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => setDismissed(loadDismissed()), []);

  function dismiss(key: string) {
    const next = [...dismissed, key];
    setDismissed(next);
    try {
      // Cap the list so a long-lived account cannot grow it without bound.
      localStorage.setItem(DISMISSED_KEY, JSON.stringify(next.slice(-200)));
    } catch {
      /* private mode: the dismissal just won't persist */
    }
  }

  const active = warnings.filter((w) => !dismissed.includes(w.key));
  if (active.length === 0) return null;

  const [lead, ...rest] = active;
  const style = STYLES[lead.severity] ?? STYLES.info;

  return (
    <GlassCard className={`mb-5 border ${style.ring}`}>
      <div className="flex items-start gap-3">
        <style.Icon size={17} className={`${style.text} mt-0.5 shrink-0`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white leading-relaxed">{lead.message}</p>

          {rest.length > 0 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 text-xs text-mist hover:text-white inline-flex items-center gap-1 transition-colors"
            >
              <ChevronRight
                size={12}
                className={`transition-transform ${expanded ? "rotate-90" : ""}`}
              />
              {expanded ? "Hide" : `${rest.length} more ${rest.length === 1 ? "nudge" : "nudges"}`}
            </button>
          )}

          {expanded && (
            <div className="mt-3 space-y-2.5 animate-in">
              {rest.map((w) => {
                const s = STYLES[w.severity] ?? STYLES.info;
                return (
                  <div key={w.key} className="flex items-start gap-2">
                    <s.Icon size={13} className={`${s.text} mt-0.5 shrink-0`} />
                    <p className="text-xs text-fog leading-relaxed flex-1 min-w-0">{w.message}</p>
                    {w.amount > 0 && (
                      <span className="ledger text-xs text-mist shrink-0">
                        {formatINR(w.amount)}
                      </span>
                    )}
                    <button
                      onClick={() => dismiss(w.key)}
                      aria-label="Dismiss"
                      className="text-mist hover:text-white shrink-0"
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <button
          onClick={() => dismiss(lead.key)}
          aria-label="Dismiss warning"
          className="text-mist hover:text-white shrink-0"
        >
          <X size={14} />
        </button>
      </div>
    </GlassCard>
  );
}
