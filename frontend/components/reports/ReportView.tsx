"use client";

/**
 * Renders any generated report.
 *
 * One component rather than seven: the reports share a shape (headline figures,
 * tables, a disclaimer), and seven near-identical layouts would drift apart.
 * Print styling lives here too, so "Save as PDF" produces the same document.
 */
import { GlassCard } from "@/components/GlassCard";
import { formatINR } from "@/lib/api";
import type { GeneratedReport } from "@/lib/types";

const PRETTY = (k: string) =>
  k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function Figure({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <p className="text-xs text-mist mb-0.5">{label}</p>
      <p className={`ledger text-lg sm:text-xl ${accent ?? "text-white"}`}>{value}</p>
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-mist border-b border-line">
            {head.map((h, i) => (
              <th key={h} className={`py-2 pr-4 font-normal ${i > 0 ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line/60 last:border-0">
              {r.map((cell, j) => (
                <td
                  key={j}
                  className={`py-2 pr-4 ${
                    j > 0 ? "text-right ledger text-fog" : "text-white"
                  }`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ReportView({ report }: { report: GeneratedReport }) {
  const d = report.data as Record<string, any>;

  if (d.empty) {
    return (
      <GlassCard>
        <p className="text-white font-medium mb-1">{report.title}</p>
        <p className="text-sm text-mist">{d.reason}</p>
      </GlassCard>
    );
  }

  return (
    <div className="report-doc space-y-4">
      <GlassCard strong className="edge-accent">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <p className="text-2xl mb-1">{report.emoji}</p>
            <h2 className="font-display text-xl font-semibold text-white">{report.title}</h2>
            <p className="text-xs text-mist mt-1">
              Generated {new Date(report.generated_at).toLocaleString()}
              {d.period ? ` · ${d.period}` : ""}
              {d.as_of ? ` · as of ${d.as_of}` : ""}
            </p>
          </div>
        </div>
      </GlassCard>

      {/* Money Wrapped */}
      {report.id === "money_wrapped" && (
        <>
          <GlassCard className="text-center py-8">
            <p className="text-xs text-mist mb-2">Your spending personality</p>
            <p className="font-display text-3xl font-semibold text-gradient mb-2">
              {d.personality}
            </p>
            <p className="text-sm text-mist max-w-md mx-auto">{d.personality_note}</p>
          </GlassCard>
          <GlassCard>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Figure label="Total spent" value={formatINR(d.total_spend)} accent="text-rose" />
              <Figure label="Total earned" value={formatINR(d.total_income)} accent="text-mint" />
              <Figure label="Savings rate" value={`${d.savings_rate}%`} />
              <Figure label="Transactions" value={String(d.transaction_count)} />
            </div>
            <div className="grid grid-cols-2 gap-4 mt-5 pt-4 border-t border-line">
              <Figure label="Biggest category" value={`${d.top_category} · ${formatINR(d.top_category_amount)}`} />
              <Figure label="Best saving month" value={`${d.best_saving_month ?? "—"} · ${formatINR(d.best_saving_amount)}`} accent="text-mint" />
            </div>
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Where it went</p>
            <Table
              head={["Category", "Amount", "Share"]}
              rows={d.categories.map((c: any) => [c.category, formatINR(c.amount), `${c.share}%`])}
            />
          </GlassCard>
        </>
      )}

      {/* Financial Health */}
      {report.id === "financial_health" && (
        <>
          <GlassCard>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Figure label="Health score" value={`${d.score}/100`} accent="text-mint" />
              <Figure label="Net worth" value={formatINR(d.net_worth)} />
              <Figure label="Assets" value={formatINR(d.total_assets)} accent="text-mint" />
              <Figure label="Liabilities" value={formatINR(d.total_liabilities)} accent="text-rose" />
            </div>
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">What drives the score</p>
            {d.score_breakdown.map((c: any) => (
              <div key={c.label} className="flex items-start justify-between gap-3 py-1.5">
                <div className="min-w-0">
                  <p className="text-sm text-white">{c.label}</p>
                  <p className="text-xs text-mist">{c.detail}</p>
                </div>
                <span className={`ledger text-sm shrink-0 ${c.points > 0 ? "text-mint" : c.points < 0 ? "text-rose" : "text-mist"}`}>
                  {c.points > 0 ? "+" : ""}{c.points}
                </span>
              </div>
            ))}
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Month by month</p>
            <Table
              head={["Month", "Income", "Spend", "Saved"]}
              rows={d.monthly.map((m: any) => [m.month, formatINR(m.income), formatINR(m.expense), formatINR(m.savings)])}
            />
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">By category</p>
            <Table
              head={["Category", "Total", "Monthly avg", "Share"]}
              rows={d.categories.map((c: any) => [c.category, formatINR(c.amount), formatINR(c.monthly_average), `${c.share}%`])}
            />
          </GlassCard>
        </>
      )}

      {/* Tax-Ready Export */}
      {report.id === "tax_ready" && (
        <>
          <GlassCard>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <Figure label="Financial year" value={d.financial_year} />
              <Figure label="Income recorded" value={formatINR(d.total_income_recorded)} accent="text-mint" />
              <Figure label="Flagged for review" value={formatINR(d.flagged_total)} accent="text-gold" />
            </div>
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-1">Deduction headroom</p>
            <p className="text-xs text-mist mb-3">
              Limits on what may be claimed — not confirmation that you qualify.
            </p>
            <Table
              head={["Section", "Limit", "Identified", "Remaining"]}
              rows={d.headroom.map((h: any) => [h.section, formatINR(h.limit), formatINR(h.identified_spend), formatINR(h.remaining)])}
            />
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Categories</p>
            {d.sections.map((s: any) => (
              <div key={s.category} className="py-2 border-b border-line/60 last:border-0">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-white">
                      {s.category}
                      {s.flagged && (
                        <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-gold/15 border border-gold/30 text-gold">
                          {s.sections.join(", ")}
                        </span>
                      )}
                    </p>
                    {s.note && <p className="text-xs text-mist mt-0.5">{s.note}</p>}
                  </div>
                  <span className="ledger text-sm text-fog shrink-0">
                    {formatINR(s.total)} · {s.count}
                  </span>
                </div>
              </div>
            ))}
          </GlassCard>
          {d.donations?.length > 0 && (
            <GlassCard>
              <p className="text-sm text-white font-medium mb-3">Donations (80G)</p>
              <Table
                head={["Date", "Recipient", "Amount"]}
                rows={d.donations.map((x: any) => [x.date, x.recipient, formatINR(x.amount)])}
              />
            </GlassCard>
          )}
        </>
      )}

      {/* Wedding Financial Plan */}
      {report.id === "wedding_plan" && (
        <>
          <GlassCard>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Figure label="Target" value={formatINR(d.goal.target)} />
              <Figure label="Saved" value={formatINR(d.goal.saved)} accent="text-mint" />
              <Figure label="Remaining" value={formatINR(d.goal.remaining)} accent="text-rose" />
              <Figure label="Monthly" value={formatINR(d.monthly_contribution)} />
            </div>
            {d.monthly_gap > 0 && (
              <p className="text-sm text-gold mt-4 pt-3 border-t border-line">
                You are {formatINR(d.monthly_gap)}/month short of the target date.
              </p>
            )}
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Ways to close the gap</p>
            {d.scenarios.map((s: any, i: number) => (
              <div key={i} className="py-2 border-b border-line/60 last:border-0">
                <p className="text-sm text-white">{s.label}</p>
                <p className="text-xs text-mist">{s.detail}</p>
              </div>
            ))}
          </GlassCard>
          {d.milestones?.length > 0 && (
            <GlassCard>
              <p className="text-sm text-white font-medium mb-3">Milestones</p>
              <Table
                head={["Month", "Saved", "Progress"]}
                rows={d.milestones.map((m: any) => [`Month ${m.month}`, formatINR(m.amount), `${m.percent}%`])}
              />
            </GlassCard>
          )}
        </>
      )}

      {/* Loan Readiness */}
      {report.id === "loan_readiness" && (
        <>
          <GlassCard>
            <p className="text-xs text-mist mb-1">Readiness</p>
            <p className="font-display text-2xl font-semibold text-gradient mb-1">{d.indicator}</p>
            <p className="text-sm text-mist">{d.summary}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 pt-4 border-t border-line">
              <Figure label="Monthly income" value={formatINR(d.monthly_income)} />
              <Figure label="Obligations" value={formatINR(d.monthly_obligations)} accent="text-rose" />
              <Figure label="Debt to income" value={`${d.debt_to_income_pct}%`} />
              <Figure label="Income stability" value={`${d.income_stability_pct}%`} />
            </div>
          </GlassCard>
          {d.obligations?.length > 0 && (
            <GlassCard>
              <p className="text-sm text-white font-medium mb-3">Existing obligations</p>
              <Table
                head={["Loan", "Balance", "Rate", "EMI"]}
                rows={d.obligations.map((o: any) => [o.name, formatINR(o.balance), `${o.rate}%`, formatINR(o.monthly_payment)])}
              />
            </GlassCard>
          )}
        </>
      )}

      {/* Net Worth Statement */}
      {report.id === "net_worth" && (
        <>
          <GlassCard>
            <div className="grid grid-cols-3 gap-4">
              <Figure label="Assets" value={formatINR(d.total_assets)} accent="text-mint" />
              <Figure label="Liabilities" value={formatINR(d.total_liabilities)} accent="text-rose" />
              <Figure label="Net worth" value={formatINR(d.net_worth)} />
            </div>
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Assets</p>
            <Table head={["Name", "Type", "Value"]}
                   rows={d.assets.map((a: any) => [a.name, a.type, formatINR(a.value)])} />
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Liabilities</p>
            <Table head={["Name", "Type", "Amount"]}
                   rows={d.liabilities.map((l: any) => [l.name, l.type, formatINR(l.amount)])} />
          </GlassCard>
        </>
      )}

      {/* Debt Payoff Plan */}
      {report.id === "debt_payoff" && (
        <>
          <GlassCard>
            <p className="text-sm text-white leading-relaxed">{d.summary}</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-4 pt-3 border-t border-line">
              <Figure label="Total debt" value={formatINR(d.total_debt)} accent="text-rose" />
              <Figure label="Interest saved" value={d.interest_saved_vs_baseline != null ? formatINR(d.interest_saved_vs_baseline) : "—"} accent="text-mint" />
              <Figure label="Months saved" value={d.months_saved_vs_baseline != null ? String(d.months_saved_vs_baseline) : "—"} accent="text-mint" />
            </div>
          </GlassCard>
          <GlassCard>
            <p className="text-sm text-white font-medium mb-3">Payoff order ({d.strategy})</p>
            <Table
              head={["#", "Debt", "Balance", "Rate", "Interest alone"]}
              rows={d.debts.map((x: any) => [
                String(x.priority), x.name, formatINR(x.balance), `${x.interest_rate}%`,
                x.interest_if_alone != null ? formatINR(x.interest_if_alone) : "—",
              ])}
            />
          </GlassCard>
        </>
      )}

      {d.disclaimer && (
        <GlassCard>
          <p className="text-xs text-mist leading-relaxed">{d.disclaimer}</p>
        </GlassCard>
      )}
    </div>
  );
}
