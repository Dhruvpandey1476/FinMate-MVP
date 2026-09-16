"use client";

/**
 * Credit Health.
 *
 * The bureau score is absent rather than mocked. A number that looks like a
 * CIBIL score but isn't one would be the most misleading thing this product
 * could show, so the card says plainly what this score is and what it is not.
 */
import { useEffect, useState } from "react";
import { ShieldCheck, TrendingDown, Info, Lock } from "lucide-react";
import { GlassCard, PageHeader, StatRow } from "@/components/GlassCard";
import { LoadingState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatINR } from "@/lib/api";
import type { CreditHealth } from "@/lib/types";

function bandColor(score: number) {
  if (score >= 80) return "text-mint";
  if (score >= 65) return "text-mint";
  if (score >= 45) return "text-gold";
  return "text-rose";
}

export default function CreditPage() {
  const [data, setData] = useState<CreditHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    api.getCreditHealth()
      .then(setData)
      .catch((err) => toast.fromError(err))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) return <LoadingState label="Assessing your credit health…" />;
  if (!data) return null;

  return (
    <ErrorBoundary>
      <PageHeader
        title="Credit Health"
        subtitle="How a lender would read your own records — computed here, not fetched from a bureau."
      />

      <div className="grid gap-4 lg:grid-cols-3 mb-5">
        <GlassCard strong className="edge-accent flex flex-col items-center justify-center py-7">
          <div className="relative w-24 h-24">
            <svg viewBox="0 0 96 96" className="w-24 h-24 -rotate-90">
              <circle cx="48" cy="48" r="40" fill="none" stroke="currentColor"
                      className="text-line" strokeWidth="8" />
              <circle
                cx="48" cy="48" r="40" fill="none" strokeWidth="8" strokeLinecap="round"
                className={bandColor(data.score)} stroke="currentColor"
                strokeDasharray={`${(data.score / 100) * 2 * Math.PI * 40} ${2 * Math.PI * 40}`}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={`ledger text-2xl font-semibold ${bandColor(data.score)}`}>
                {data.score}
              </span>
            </div>
          </div>
          <p className={`text-sm font-medium mt-3 ${bandColor(data.score)}`}>{data.band}</p>
          <p className="text-xs text-mist mt-1 text-center max-w-[220px]">{data.band_note}</p>
        </GlassCard>

        <GlassCard className="lg:col-span-2">
          <p className="text-sm text-white font-medium mb-3">What moves it</p>
          {data.factors.map((f) => (
            <div key={f.label} className="flex items-start justify-between gap-3 py-2 border-b border-line last:border-0">
              <div className="min-w-0">
                <p className="text-sm text-white">
                  {f.label} <span className="text-mist">· {f.value}</span>
                </p>
                <p className="text-xs text-mist leading-snug">{f.detail}</p>
              </div>
              <span className={`ledger text-sm shrink-0 ${f.points < 0 ? "text-rose" : "text-mint"}`}>
                {f.points === 0 ? "—" : f.points}
              </span>
            </div>
          ))}
        </GlassCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2 mb-5">
        <GlassCard>
          <p className="text-sm text-white font-medium mb-3">The numbers</p>
          <StatRow label="Monthly income" value={formatINR(data.monthly_income)} />
          <StatRow label="Monthly obligations" value={formatINR(data.monthly_obligations)} accent="text-rose" />
          <StatRow label="Debt to income" value={`${data.debt_to_income_pct}%`} />
          <StatRow label="Card utilisation" value={`${data.utilisation_pct}%`} />
          <StatRow label="Total debt" value={formatINR(data.total_debt)} accent="text-rose" />
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown size={15} className="text-mint" />
            <p className="text-sm text-white font-medium">How to improve it</p>
          </div>
          {data.improvements.map((i, idx) => (
            <div key={idx} className="py-2 border-b border-line last:border-0">
              <p className="text-sm text-white">{i.action}</p>
              <p className="text-xs text-mist">{i.why}</p>
            </div>
          ))}
        </GlassCard>
      </div>

      {data.obligations.length > 0 && (
        <GlassCard className="mb-5">
          <p className="text-sm text-white font-medium mb-3">Your obligations</p>
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-mist border-b border-line">
                  <th className="py-2 pr-4 font-normal">Name</th>
                  <th className="py-2 pr-4 font-normal text-right">Balance</th>
                  <th className="py-2 pr-4 font-normal text-right">Rate</th>
                  <th className="py-2 pr-4 font-normal text-right">EMI</th>
                </tr>
              </thead>
              <tbody>
                {data.obligations.map((o) => (
                  <tr key={o.name} className="border-b border-line/60 last:border-0">
                    <td className="py-2 pr-4 text-white">{o.name}</td>
                    <td className="py-2 pr-4 text-right ledger text-fog">{formatINR(o.balance)}</td>
                    <td className="py-2 pr-4 text-right ledger text-fog">{o.rate}%</td>
                    <td className="py-2 pr-4 text-right ledger text-fog">{formatINR(o.monthly_payment)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}

      {/* Absent, not mocked. */}
      <GlassCard className="border border-line">
        <div className="flex items-start gap-3">
          <Lock size={16} className="text-mist mt-0.5 shrink-0" />
          <div>
            <p className="text-sm text-white font-medium mb-1">
              Bureau score — not available
            </p>
            <p className="text-sm text-mist leading-relaxed">{data.bureau_note}</p>
          </div>
        </div>
      </GlassCard>
    </ErrorBoundary>
  );
}
