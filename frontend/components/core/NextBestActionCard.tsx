"use client";

/**
 * Next Best Action.
 *
 * One card, one action. The raw candidate feed deliberately does not appear
 * here - it still lives on Insights and Goals for users who want the detail.
 * A dashboard showing twelve competing suggestions is a dashboard that decides
 * nothing for the user.
 *
 * The "how this was chosen" disclosure exposes the deterministic score and the
 * runners-up. It is there because the separation between ranking (code) and
 * phrasing (model) is a claim worth making checkable rather than asserted.
 */
import { useState } from "react";
import { Sparkles, ChevronDown, RefreshCw, TrendingUp, Clock } from "lucide-react";
import { GlassCard } from "@/components/GlassCard";
import { useToast } from "@/components/Toast";
import { api, formatINR } from "@/lib/api";
import type { NextBestAction } from "@/lib/types";

const SOURCE_LABEL: Record<string, string> = {
  opportunity_discovery: "Opportunity Discovery",
  goal_planner: "Goal Planner",
  safe_to_spend: "Safe-to-Spend",
  financial_twin: "Financial Twin",
};

export default function NextBestActionCard({
  data,
  onRefreshed,
}: {
  data: NextBestAction;
  onRefreshed: (next: NextBestAction) => void;
}) {
  const [showHow, setShowHow] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function refresh() {
    setBusy(true);
    try {
      onRefreshed(await api.getNextBestAction(true));
    } catch (err) {
      toast.fromError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <GlassCard strong className="edge-accent">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles size={15} className="text-violet shrink-0" />
          <p className="text-sm text-fog">Your next best action</p>
        </div>
        <button
          onClick={refresh}
          disabled={busy}
          aria-label="Recalculate"
          className="text-mist hover:text-white transition-colors disabled:opacity-50 shrink-0"
        >
          <RefreshCw size={13} className={busy ? "animate-spin" : ""} />
        </button>
      </div>

      <p className="text-lg sm:text-xl text-white font-medium leading-snug mb-2 text-balance">
        {data.action_text}
      </p>
      <p className="text-sm text-mist leading-relaxed">{data.why_text}</p>

      {(data.estimated_impact > 0 || (data.estimated_impact_months ?? 0) > 0) && (
        <div className="flex flex-wrap items-center gap-2 mt-4">
          {data.estimated_impact > 0 && (
            <span className="text-xs px-2.5 py-1 rounded-full bg-mint/10 border border-mint/25 text-mint inline-flex items-center gap-1.5">
              <TrendingUp size={11} />
              {formatINR(data.estimated_impact)}/month
            </span>
          )}
          {(data.estimated_impact_months ?? 0) > 0 && (
            <span className="text-xs px-2.5 py-1 rounded-full bg-violet/10 border border-violet/25 text-violet inline-flex items-center gap-1.5">
              <Clock size={11} />
              {data.estimated_impact_months} months sooner
            </span>
          )}
        </div>
      )}

      <button
        onClick={() => setShowHow((v) => !v)}
        aria-expanded={showHow}
        className="mt-4 text-xs text-mist hover:text-white inline-flex items-center gap-1.5 transition-colors"
      >
        <ChevronDown size={12} className={`transition-transform ${showHow ? "rotate-180" : ""}`} />
        How this was chosen
      </button>

      {showHow && (
        <div className="mt-3 pt-3 border-t border-line space-y-2 animate-in">
          <p className="text-xs text-mist leading-relaxed">
            {data.considered} candidate action{data.considered === 1 ? "" : "s"} were scored by a
            deterministic function on impact, effort and urgency. The highest score won.
            The AI wrote the wording — it did not make the choice.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            <span className="text-mist">
              Source: <span className="text-fog">{SOURCE_LABEL[data.source_module ?? ""] ?? data.source_module ?? "—"}</span>
            </span>
            {data.score !== undefined && (
              <span className="text-mist">
                Score: <span className="ledger text-fog">{data.score}</span>
              </span>
            )}
            <span className="text-mist">
              Decided by: <span className="text-fog">{data.decided_by}</span>
            </span>
          </div>

          {data.runners_up && data.runners_up.length > 0 && (
            <div className="pt-1">
              <p className="text-xs text-mist mb-1">Runners-up</p>
              {data.runners_up.map((r, i) => (
                <div key={i} className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-mist truncate">{r.action_text}</span>
                  <span className="ledger text-mist/70 shrink-0">{r.score}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}
