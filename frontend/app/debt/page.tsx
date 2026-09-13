"use client";

import { useEffect, useState } from "react";
import { Landmark, Plus, Trash2, TrendingDown, Scale, Lock } from "lucide-react";
import { GlassCard, PageHeader, StatRow } from "@/components/GlassCard";
import { LoadingState, EmptyState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatINR, ApiError } from "@/lib/api";
import type { DebtPlan } from "@/lib/types";

interface Liability {
  id: number;
  name: string;
  liability_type: string;
  amount: number;
  interest_rate: number;
  monthly_payment: number;
}

const BLANK = {
  name: "", liability_type: "loan", amount: 0, interest_rate: 0, monthly_payment: 0,
};

export default function DebtPage() {
  const [liabilities, setLiabilities] = useState<Liability[]>([]);
  const [plan, setPlan] = useState<DebtPlan | null>(null);
  const [extra, setExtra] = useState(5000);
  const [strategy, setStrategy] = useState<"avalanche" | "snowball">("avalanche");
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ ...BLANK });
  const toast = useToast();

  async function load() {
    setLoading(true);
    try {
      const list = await api.getLiabilities();
      setLiabilities(list);
      if (list.length > 0) {
        const p = await api.getDebtPlan(extra, strategy);
        setPlan(p);
        setLocked(false);
      } else {
        setPlan(null);
      }
    } catch (err) {
      if (err instanceof ApiError && err.isQuotaExceeded) {
        // Paid feature: show the upsell instead of an error.
        setLocked(true);
      } else {
        toast.fromError(err);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extra, strategy]);

  async function addLiability(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim() || form.amount <= 0) {
      toast.error("A name and a balance above zero are required.");
      return;
    }
    try {
      await api.addLiability(form);
      setForm({ ...BLANK });
      setAdding(false);
      toast.success("Debt added");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteLiability(id);
      toast.success("Removed");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  if (loading && !plan && liabilities.length === 0 && !locked) {
    return <LoadingState label="Building your payoff plan…" />;
  }

  return (
    <ErrorBoundary>
      <PageHeader
        title="Debt Optimizer"
        subtitle="Which loan to kill first, and what an extra rupee a month actually buys you."
      />

      {locked && (
        <GlassCard strong className="mb-5 border border-gold/30">
          <div className="flex items-start gap-3">
            <Lock size={18} className="text-gold mt-0.5 shrink-0" />
            <div>
              <p className="text-white font-medium mb-1">Available on Plus</p>
              <p className="text-sm text-mist">
                The debt optimiser runs full amortisation across every loan and
                compares prepaying against investing. Upgrade to unlock it.
              </p>
            </div>
          </div>
        </GlassCard>
      )}

      <GlassCard className="mb-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Landmark size={15} className="text-violet" />
            <p className="text-sm text-white font-medium">Your debts</p>
          </div>
          <button
            onClick={() => setAdding((a) => !a)}
            className="text-xs px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-1.5"
          >
            <Plus size={12} /> Add debt
          </button>
        </div>

        {adding && (
          <form onSubmit={addLiability} className="grid gap-2 sm:grid-cols-5 mb-4 p-3 rounded-xl bg-white/[0.03] border border-line">
            <input
              placeholder="Name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="sm:col-span-2 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <input
              type="number" placeholder="Balance" value={form.amount || ""}
              onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <input
              type="number" step="0.1" placeholder="Rate %" value={form.interest_rate || ""}
              onChange={(e) => setForm({ ...form, interest_rate: Number(e.target.value) })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <input
              type="number" placeholder="EMI" value={form.monthly_payment || ""}
              onChange={(e) => setForm({ ...form, monthly_payment: Number(e.target.value) })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <button
              type="submit"
              className="sm:col-span-5 text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent font-medium"
            >
              Save debt
            </button>
          </form>
        )}

        {liabilities.length === 0 ? (
          <p className="text-sm text-mist py-3">
            No debts recorded. Add a loan with its interest rate and EMI to see a payoff plan.
          </p>
        ) : (
          <div className="space-y-0">
            {liabilities.map((l) => (
              <div key={l.id} className="flex items-center justify-between py-2.5 border-b border-line last:border-0">
                <div className="min-w-0">
                  <p className="text-sm text-white truncate">{l.name}</p>
                  <p className="text-xs text-mist">
                    {l.interest_rate}% · EMI {formatINR(l.monthly_payment)}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-3">
                  <span className="ledger text-sm text-white">{formatINR(l.amount)}</span>
                  <button
                    onClick={() => remove(l.id)}
                    aria-label={`Delete ${l.name}`}
                    className="text-mist hover:text-rose transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {plan && plan.debts.length > 0 && (
        <>
          <GlassCard strong className="mb-5">
            <p className="text-sm text-white leading-relaxed">{plan.summary}</p>
          </GlassCard>

          <div className="grid gap-4 md:grid-cols-3 mb-5">
            <GlassCard>
              <p className="text-xs text-mist mb-1">Total debt</p>
              <p className="ledger text-xl text-rose">{formatINR(plan.total_debt)}</p>
            </GlassCard>
            <GlassCard>
              <p className="text-xs text-mist mb-1">Interest saved</p>
              <p className="ledger text-xl text-mint">
                {plan.interest_saved_vs_baseline !== null
                  ? formatINR(plan.interest_saved_vs_baseline)
                  : "—"}
              </p>
            </GlassCard>
            <GlassCard>
              <p className="text-xs text-mist mb-1">Months saved</p>
              <p className="ledger text-xl text-mint">
                {plan.months_saved_vs_baseline ?? "—"}
              </p>
            </GlassCard>
          </div>

          <GlassCard className="mb-5">
            <div className="flex flex-wrap items-center gap-4 justify-between">
              <div className="flex-1 min-w-[240px]">
                <label className="text-xs text-mist block mb-2">
                  Extra per month: <span className="ledger text-white">{formatINR(extra)}</span>
                </label>
                <input
                  type="range" min={0} max={50000} step={1000} value={extra}
                  onChange={(e) => setExtra(Number(e.target.value))}
                  className="w-full accent-mint"
                />
              </div>
              <div className="flex gap-1">
                {(["avalanche", "snowball"] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setStrategy(s)}
                    className={`text-xs px-3 py-1.5 rounded-lg border capitalize transition-colors ${
                      strategy === s
                        ? "border-mint/50 text-mint bg-mint/10"
                        : "border-line text-mist hover:text-white"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {plan.avalanche_advantage !== null && plan.avalanche_advantage > 0 && (
              <div className="mt-4 flex items-start gap-2 text-xs text-mist pt-3 border-t border-line">
                <Scale size={13} className="text-gold mt-0.5 shrink-0" />
                <span>
                  Avalanche (highest rate first) costs{" "}
                  <span className="text-gold">{formatINR(plan.avalanche_advantage)}</span> less
                  in interest than snowball. Snowball clears small balances sooner, which some
                  people find easier to stick to — the gap above is what that comfort costs.
                </span>
              </div>
            )}
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-2 mb-3">
              <TrendingDown size={15} className="text-mint" />
              <p className="text-sm text-white font-medium">
                Payoff order ({strategy})
              </p>
            </div>
            <div className="space-y-0">
              {plan.debts.map((d) => (
                <div key={d.id} className="flex items-center justify-between py-3 border-b border-line last:border-0">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="w-6 h-6 rounded-lg bg-white/[0.05] border border-line flex items-center justify-center text-xs text-mint shrink-0">
                      {d.priority}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm text-white truncate">{d.name}</p>
                      <p className="text-xs text-mist">
                        {formatINR(d.balance)} at {d.interest_rate}%
                        {d.payoff_month_in_plan
                          ? ` · clear in month ${d.payoff_month_in_plan}`
                          : ""}
                      </p>
                    </div>
                  </div>
                  <div className="text-right shrink-0 ml-3">
                    <p className="ledger text-sm text-white">
                      {d.interest_if_alone !== null ? formatINR(d.interest_if_alone) : "—"}
                    </p>
                    <p className="text-xs text-mist">interest if alone</p>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        </>
      )}
    </ErrorBoundary>
  );
}
