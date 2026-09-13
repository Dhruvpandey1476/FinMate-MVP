"use client";

import { useEffect, useState } from "react";
import { Activity, Info } from "lucide-react";
import { PageHeader, GlassCard, StatRow } from "@/components/GlassCard";
import { LoadingState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { useChartTheme } from "@/lib/chartTheme";
import { api, formatINR, formatDate } from "@/lib/api";
import type { Snapshot, Transaction } from "@/lib/types";

interface Asset { id: number; name: string; asset_type: string; value: number }
interface Liability {
  id: number; name: string; liability_type: string;
  amount: number; interest_rate: number; monthly_payment: number;
}

function scoreColor(score: number) {
  if (score >= 70) return "text-mint";
  if (score >= 45) return "text-gold";
  return "text-rose";
}

export default function FinancialTwinPage() {
  const ct = useChartTheme();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [liabilities, setLiabilities] = useState<Liability[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getSnapshot(),
      api.getAssets(),
      api.getLiabilities(),
      api.getTransactions(20),
    ])
      .then(([s, a, l, t]) => {
        if (cancelled) return;
        setSnapshot(s);
        setAssets(a);
        setLiabilities(l);
        setTransactions(t);
      })
      .catch((err) => !cancelled && toast.fromError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !snapshot) return <LoadingState label="Loading your financial twin…" />;

  const score = snapshot?.financial_health_score ?? 0;

  return (
    <ErrorBoundary>
      <PageHeader
        title="Financial Twin"
        subtitle="A continuously updated mirror of your financial state."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5 mb-6">
        <GlassCard>
          <p className="text-sm text-fog mb-2">Assets</p>
          {assets.length === 0 ? (
            <p className="text-sm text-mist py-2">Nothing recorded yet.</p>
          ) : (
            assets.map((a) => (
              <StatRow key={a.id} label={a.name} value={formatINR(a.value)} accent="text-mint" />
            ))
          )}
          <div className="pt-2 mt-1 border-t border-line flex justify-between">
            <span className="text-sm text-white font-medium">Total</span>
            <span className="ledger text-mint font-semibold">
              {formatINR(snapshot?.total_assets ?? 0)}
            </span>
          </div>
        </GlassCard>

        <GlassCard>
          <p className="text-sm text-fog mb-2">Liabilities</p>
          {liabilities.length === 0 ? (
            <p className="text-sm text-mist py-2">No debts recorded.</p>
          ) : (
            liabilities.map((l) => (
              <StatRow
                key={l.id}
                label={`${l.name} (${l.interest_rate}% APR)`}
                value={formatINR(l.amount)}
                accent="text-rose"
              />
            ))
          )}
          <div className="pt-2 mt-1 border-t border-line flex justify-between">
            <span className="text-sm text-white font-medium">Total</span>
            <span className="ledger text-rose font-semibold">
              {formatINR(snapshot?.total_liabilities ?? 0)}
            </span>
          </div>
        </GlassCard>

        <GlassCard strong className="edge-accent">
          <p className="text-sm text-fog mb-2">Net Worth</p>
          <p className="ledger text-3xl font-semibold text-gradient">
            {formatINR(snapshot?.net_worth ?? 0)}
          </p>
          <div className="mt-4 space-y-1">
            <StatRow
              label="Income (this month)"
              value={formatINR(snapshot?.total_income_month ?? 0)}
              accent="text-mint"
            />
            <StatRow
              label="Expenses (this month)"
              value={formatINR(snapshot?.total_expense_month ?? 0)}
              accent="text-rose"
            />
            <StatRow label="Savings Rate" value={`${snapshot?.savings_rate ?? 0}%`} />
          </div>
        </GlassCard>
      </div>

      {/* The health score is the hero number, so it ships with its own audit
          trail rather than appearing as an unexplained integer. */}
      <GlassCard className="mb-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5 lg:gap-8">
          <div className="flex items-center gap-4">
            <div className="relative w-20 h-20 shrink-0">
              <svg viewBox="0 0 80 80" className="w-20 h-20 -rotate-90">
                <circle cx="40" cy="40" r="34" fill="none" stroke={ct.grid} strokeWidth="7" />
                <circle
                  cx="40" cy="40" r="34" fill="none" strokeWidth="7" strokeLinecap="round"
                  stroke={score >= 70 ? ct.mint : score >= 45 ? ct.gold : ct.rose}
                  strokeDasharray={`${(score / 100) * 2 * Math.PI * 34} ${2 * Math.PI * 34}`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`ledger text-xl font-semibold ${scoreColor(score)}`}>{score}</span>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <Activity size={15} className="text-mint" />
                <p className="text-sm text-white font-medium">Financial Health Score</p>
              </div>
              <p className="text-xs text-mist mt-1 max-w-xs leading-relaxed">
                A transparent composite — every factor below shows exactly what it
                contributed, so you know what to move.
              </p>
            </div>
          </div>

          <div className="flex-1 min-w-0 w-full space-y-2.5">
            {(snapshot?.health_breakdown ?? []).map((c) => (
              <div key={c.label} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-white">{c.label}</p>
                  <p className="text-xs text-mist leading-snug">{c.detail}</p>
                </div>
                <span
                  className={`ledger text-sm shrink-0 ${
                    c.points > 0 ? "text-mint" : c.points < 0 ? "text-rose" : "text-mist"
                  }`}
                >
                  {c.points > 0 ? "+" : ""}
                  {c.points}
                </span>
              </div>
            ))}
          </div>
        </div>
      </GlassCard>

      <GlassCard>
        <p className="text-sm text-fog mb-3">Recent Transactions</p>
        {transactions.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-mist py-3">
            <Info size={14} />
            No transactions yet — upload a statement or add one manually.
          </div>
        ) : (
          <div className="overflow-x-auto scrollbar-thin -mx-1 px-1">
            <table className="w-full text-sm stack-table">
              <thead>
                <tr className="text-left text-mist border-b border-line">
                  <th className="py-2 pr-4 font-normal">Date</th>
                  <th className="py-2 pr-4 font-normal">Category</th>
                  <th className="py-2 pr-4 font-normal">Merchant</th>
                  <th className="py-2 pr-4 font-normal text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className="border-b border-line/60 last:border-0">
                    <td data-cell="date" className="py-2 pr-4 text-mist whitespace-nowrap text-xs sm:text-sm order-2">{formatDate(t.date)}</td>
                    <td data-cell="category" className="py-2 pr-4 text-white font-medium">{t.category}</td>
                    <td data-cell="merchant" className="py-2 pr-4 text-mist hidden sm:table-cell">{t.merchant || "—"}</td>
                    <td
                      data-cell="amount"
                      className={`py-2 pr-4 ledger text-right whitespace-nowrap ${
                        t.amount >= 0 ? "text-mint" : "text-rose"
                      }`}
                    >
                      {t.amount >= 0 ? "+" : ""}
                      {formatINR(t.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </ErrorBoundary>
  );
}
