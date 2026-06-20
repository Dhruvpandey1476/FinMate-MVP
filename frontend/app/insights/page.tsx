"use client";

import { useEffect, useState } from "react";
import { Repeat, TrendingDown, AlertCircle } from "lucide-react";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { api, formatINR } from "@/lib/api";

const TYPE_META: Record<string, { icon: any; color: string; label: string }> = {
  subscription: { icon: Repeat, color: "text-violet", label: "Subscription" },
  spending_leak: { icon: TrendingDown, color: "text-rose", label: "Spending Leak" },
  unusual_spending: { icon: AlertCircle, color: "text-gold", label: "Unusual Spending" },
};

export default function InsightsPage() {
  const [insights, setInsights] = useState<any[]>([]);

  useEffect(() => {
    api.getInsights().then(setInsights).catch(() => {});
  }, []);

  const totalImpact = insights.reduce((sum, i) => sum + (i.monthly_impact || 0), 0);

  return (
    <div>
      <PageHeader title="Opportunity Discovery" subtitle="Spending leaks, unused subscriptions, and savings opportunities — found automatically." />

      <GlassCard strong className="mb-6">
        <p className="text-sm text-fog mb-1">Total monthly opportunity found</p>
        <p className="ledger text-3xl font-semibold text-mint">{formatINR(totalImpact)}</p>
        <p className="text-xs text-mist mt-1">Across {insights.length} detected opportunities this month.</p>
      </GlassCard>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {insights.map((ins, i) => {
          const meta = TYPE_META[ins.type] || TYPE_META.spending_leak;
          const Icon = meta.icon;
          return (
            <GlassCard key={i}>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-lg bg-white/[0.05] flex items-center justify-center shrink-0">
                  <Icon size={16} className={meta.color} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase tracking-wide text-mist">{meta.label}</span>
                    {ins.monthly_impact > 0 && (
                      <span className="ledger text-xs text-mint">+{formatINR(ins.monthly_impact, { compact: true })}/mo</span>
                    )}
                  </div>
                  <p className="text-sm text-white font-medium mt-1">{ins.title}</p>
                  <p className="text-xs text-mist mt-1 leading-relaxed">{ins.description}</p>
                </div>
              </div>
            </GlassCard>
          );
        })}
        {insights.length === 0 && <p className="text-sm text-mist">No opportunities detected yet.</p>}
      </div>
    </div>
  );
}
