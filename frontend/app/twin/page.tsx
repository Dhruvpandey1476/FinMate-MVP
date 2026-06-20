"use client";

import { useEffect, useState } from "react";
import { PageHeader, GlassCard, StatRow } from "@/components/GlassCard";
import { api, formatINR } from "@/lib/api";

export default function FinancialTwinPage() {
  const [snapshot, setSnapshot] = useState<any>(null);
  const [assets, setAssets] = useState<any[]>([]);
  const [liabilities, setLiabilities] = useState<any[]>([]);
  const [transactions, setTransactions] = useState<any[]>([]);

  useEffect(() => {
    api.getSnapshot().then(setSnapshot).catch(() => {});
    api.getAssets().then(setAssets).catch(() => {});
    api.getLiabilities().then(setLiabilities).catch(() => {});
    api.getTransactions(20).then(setTransactions).catch(() => {});
  }, []);

  return (
    <div>
      <PageHeader title="Financial Twin" subtitle="A continuously updated mirror of your financial state." />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">
        <GlassCard>
          <p className="text-sm text-fog mb-2">Assets</p>
          {assets.map((a) => (
            <StatRow key={a.id} label={a.name} value={formatINR(a.value)} accent="text-mint" />
          ))}
          <div className="pt-2 mt-1 border-t border-line flex justify-between">
            <span className="text-sm text-white font-medium">Total</span>
            <span className="ledger text-mint font-semibold">{formatINR(snapshot?.total_assets || 0)}</span>
          </div>
        </GlassCard>

        <GlassCard>
          <p className="text-sm text-fog mb-2">Liabilities</p>
          {liabilities.map((l) => (
            <StatRow key={l.id} label={`${l.name} (${l.interest_rate}% APR)`} value={formatINR(l.amount)} accent="text-rose" />
          ))}
          <div className="pt-2 mt-1 border-t border-line flex justify-between">
            <span className="text-sm text-white font-medium">Total</span>
            <span className="ledger text-rose font-semibold">{formatINR(snapshot?.total_liabilities || 0)}</span>
          </div>
        </GlassCard>

        <GlassCard strong>
          <p className="text-sm text-fog mb-2">Net Worth</p>
          <p className="ledger text-3xl font-semibold text-white">{formatINR(snapshot?.net_worth || 0)}</p>
          <div className="mt-4 space-y-1">
            <StatRow label="Income (this month)" value={formatINR(snapshot?.total_income_month || 0)} accent="text-mint" />
            <StatRow label="Expenses (this month)" value={formatINR(snapshot?.total_expense_month || 0)} accent="text-rose" />
            <StatRow label="Savings Rate" value={`${snapshot?.savings_rate || 0}%`} />
          </div>
        </GlassCard>
      </div>

      <GlassCard>
        <p className="text-sm text-fog mb-3">Recent Transactions</p>
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">
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
                  <td className="py-2 pr-4 text-mist">{new Date(t.date).toLocaleDateString("en-IN")}</td>
                  <td className="py-2 pr-4 text-white">{t.category}</td>
                  <td className="py-2 pr-4 text-mist">{t.merchant || "—"}</td>
                  <td className={`py-2 pr-4 ledger text-right ${t.amount >= 0 ? "text-mint" : "text-rose"}`}>
                    {t.amount >= 0 ? "+" : ""}{formatINR(t.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
