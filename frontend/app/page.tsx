"use client";

import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { TrendingUp, TrendingDown, AlertTriangle, Sparkle } from "lucide-react";
import { GlassCard, PageHeader } from "@/components/GlassCard";
import { api, formatINR } from "@/lib/api";

export default function Dashboard() {
  const [snapshot, setSnapshot] = useState<any>(null);
  const [series, setSeries] = useState<any[]>([]);
  const [goals, setGoals] = useState<any[]>([]);
  const [insights, setInsights] = useState<any[]>([]);
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    api.getSnapshot().then(setSnapshot).catch(() => {});
    api.getCashflowSeries(6).then(setSeries).catch(() => {});
    api.getGoals().then(setGoals).catch(() => {});
    api.getInsights().then((d) => setInsights(d.slice(0, 3))).catch(() => {});
    api.getUser().then(setUser).catch(() => {});
  }, []);

  if (!snapshot) {
    return <div className="text-mist">Loading your financial twin…</div>;
  }

  const score = snapshot.financial_health_score;
  const cashFlowPositive = snapshot.cash_flow >= 0;

  return (
    <div>
      <PageHeader
        title={`Welcome back${user?.name ? `, ${user.name.split(" ")[0]}` : ""}`}
        subtitle="Your Financial Digital Twin, updated in real time."
      />

      {/* Hero row: Health Score gauge + key stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">
        <GlassCard strong className="lg:col-span-1 flex flex-col items-center justify-center">
          <HealthGauge score={score} />
          <p className="text-sm text-fog mt-3">Financial Health Score</p>
        </GlassCard>

        <GlassCard className="lg:col-span-2">
          <p className="text-sm text-fog mb-4">6-Month Cash Flow</p>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={series}>
              <defs>
                <linearGradient id="income" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#27E0A6" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#27E0A6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="expense" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#FF6B7A" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#FF6B7A" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1E2740" vertical={false} />
              <XAxis dataKey="month" stroke="#5E6A87" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#5E6A87" fontSize={11} tickLine={false} axisLine={false}
                tickFormatter={(v) => formatINR(v, { compact: true })} />
              <Tooltip
                contentStyle={{ background: "#11172A", border: "1px solid #1E2740", borderRadius: 12, fontSize: 12 }}
                formatter={(v: number) => formatINR(v)}
              />
              <Area type="monotone" dataKey="income" stroke="#27E0A6" fill="url(#income)" strokeWidth={2} />
              <Area type="monotone" dataKey="expense" stroke="#FF6B7A" fill="url(#expense)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label="Net Worth" value={formatINR(snapshot.net_worth)} icon={<Sparkle size={15} />} />
        <StatCard
          label="Savings Rate"
          value={`${snapshot.savings_rate}%`}
          icon={snapshot.savings_rate >= 20 ? <TrendingUp size={15} className="text-mint" /> : <TrendingDown size={15} className="text-rose" />}
        />
        <StatCard
          label="Monthly Cash Flow"
          value={formatINR(snapshot.cash_flow)}
          accent={cashFlowPositive ? "text-mint" : "text-rose"}
        />
        <StatCard label="Total Liabilities" value={formatINR(snapshot.total_liabilities)} accent="text-rose" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Goal Progress */}
        <GlassCard>
          <p className="text-sm text-fog mb-4">Goal Progress</p>
          <div className="space-y-4">
            {goals.map((g) => {
              const pct = Math.min((g.current_amount / g.target_amount) * 100, 100);
              return (
                <div key={g.id}>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-white">{g.name}</span>
                    <span className="ledger text-fog">{formatINR(g.current_amount, { compact: true })} / {formatINR(g.target_amount, { compact: true })}</span>
                  </div>
                  <div className="h-2 rounded-full bg-line overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-mint to-violet" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>

        {/* Recent Insights / Upcoming Risks */}
        <GlassCard>
          <p className="text-sm text-fog mb-4">Recent Insights &amp; Risks</p>
          <div className="space-y-3">
            {insights.map((ins, i) => (
              <div key={i} className="flex gap-3 items-start p-3 rounded-xl bg-white/[0.03] border border-line">
                <AlertTriangle size={16} className="text-gold mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm text-white font-medium">{ins.title}</p>
                  <p className="text-xs text-mist mt-0.5">{ins.description}</p>
                </div>
              </div>
            ))}
            {insights.length === 0 && <p className="text-sm text-mist">No insights yet — check back after a few weeks of activity.</p>}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon, accent }: { label: string; value: string; icon?: React.ReactNode; accent?: string }) {
  return (
    <GlassCard className="!p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-mist">{label}</span>
        {icon}
      </div>
      <p className={`ledger text-xl font-semibold ${accent || "text-white"}`}>{value}</p>
    </GlassCard>
  );
}

function HealthGauge({ score }: { score: number }) {
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 70 ? "#27E0A6" : score >= 40 ? "#F0B860" : "#FF6B7A";

  return (
    <svg width="160" height="160" viewBox="0 0 160 160">
      <circle cx="80" cy="80" r={radius} stroke="#1E2740" strokeWidth="10" fill="none" />
      <circle
        cx="80" cy="80" r={radius}
        stroke={color} strokeWidth="10" fill="none"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 80 80)"
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
      <text x="80" y="76" textAnchor="middle" className="ledger" fontSize="32" fill="white" fontWeight="600">
        {score}
      </text>
      <text x="80" y="98" textAnchor="middle" fontSize="11" fill="#5E6A87">
        / 100
      </text>
    </svg>
  );
}
