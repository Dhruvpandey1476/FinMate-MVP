"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { TrendingUp, TrendingDown, AlertTriangle, Sparkle, Clock } from "lucide-react";
import { GlassCard, PageHeader } from "@/components/GlassCard";
import { LoadingState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { useChartTheme, tooltipStyle } from "@/lib/chartTheme";
import { api, formatINR } from "@/lib/api";
import SafeToSpendHero from "@/components/core/SafeToSpendHero";
import EarlyWarningBanner from "@/components/core/EarlyWarningBanner";
import TimeMachine from "@/components/core/TimeMachine";
import NextBestActionCard from "@/components/core/NextBestActionCard";
import type {
  Snapshot, CashflowPoint, Goal, Insight, User, Forecast, CoreLoop,
  SafeToSpend, TimeMachine as TimeMachineData, NextBestAction,
} from "@/lib/types";

export default function Dashboard() {
  const ct = useChartTheme();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [series, setSeries] = useState<CashflowPoint[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  // The Core Loop arrives in one request so the hero renders together rather
  // than popping in four separate times.
  const [core, setCore] = useState<CoreLoop | null>(null);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;

    // The snapshot gates the whole page, so a failure there is surfaced.
    api.getSnapshot()
      .then((s) => !cancelled && setSnapshot(s))
      .catch((err) => !cancelled && toast.fromError(err));

    // The rest are enrichments: degrade quietly rather than burying the page
    // in toasts if one optional panel is unavailable.
    api.getCashflowSeries(6).then((d) => !cancelled && setSeries(d)).catch(() => {});
    api.getGoals().then((d) => !cancelled && setGoals(d)).catch(() => {});
    api.getInsights().then((d) => !cancelled && setInsights(d.slice(0, 3))).catch(() => {});
    api.getUser().then((d) => !cancelled && setUser(d)).catch(() => {});
    api.getForecast(90).then((d) => !cancelled && setForecast(d)).catch(() => {});
    api.getCoreLoop().then((d) => !cancelled && setCore(d)).catch(() => {});

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [loadingSample, setLoadingSample] = useState(false);

  // Measure chart width from the real DOM (ResponsiveContainer renders blank
  // inside CSS grid because it can't resolve its own width).
  const [chartW, setChartW] = useState(0);
  const roRef = useRef<ResizeObserver | null>(null);
  const chartRef = useCallback((node: HTMLDivElement | null) => {
    if (roRef.current) {
      roRef.current.disconnect();
      roRef.current = null;
    }
    if (node) {
      const ro = new ResizeObserver((entries) => setChartW(entries[0].contentRect.width));
      ro.observe(node);
      roRef.current = ro;
      setChartW(node.clientWidth);
    }
  }, []);

  async function loadSample() {
    setLoadingSample(true);
    try {
      await api.loadSample();
      window.location.reload();
    } catch (err) {
      toast.fromError(err);
      setLoadingSample(false);
    }
  }

  if (!snapshot) {
    return <LoadingState label="Loading your financial twin…" />;
  }

  const isEmpty = snapshot.net_worth === 0 && snapshot.total_income_month === 0 && goals.length === 0;
  if (isEmpty) {
    return (
      <div>
        <PageHeader
          title={`Welcome${user?.name ? `, ${user.name.split(" ")[0]}` : ""}`}
          subtitle="Let's build your Financial Twin."
        />
        <GlassCard strong className="max-w-xl">
          <p className="text-white font-medium mb-1">Let's build your Financial Twin</p>
          <p className="text-sm text-mist mb-5">
            No bank statement needed — a 30-second setup gives your AI CFO enough to
            start. Or upload a statement for full precision, or explore with sample data.
          </p>
          <div className="flex flex-wrap gap-3">
            <a href="/onboarding" className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-mint to-violet text-onaccent font-medium text-sm">
              Quick setup (30s)
            </a>
            <a href="/upload" className="px-4 py-2.5 rounded-xl border border-line text-sm text-white hover:bg-white/[0.04]">
              Upload statement
            </a>
            <button
              onClick={loadSample}
              disabled={loadingSample}
              className="px-4 py-2.5 rounded-xl border border-line text-sm text-white hover:bg-white/[0.04] disabled:opacity-60"
            >
              {loadingSample ? "Loading…" : "Load sample data"}
            </button>
          </div>
        </GlassCard>
      </div>
    );
  }

  const score = snapshot.financial_health_score;
  const cashFlowPositive = snapshot.cash_flow >= 0;

  return (
    <div>
      <PageHeader
        title={`Welcome back${user?.name ? `, ${user.name.split(" ")[0]}` : ""}`}
        subtitle="Your Financial Digital Twin, updated in real time."
      />

      {/* ---- Core Loop: understand -> warn -> predict -> decide ----
           This ordering is the product thesis made visible. Everything below
           it (health gauge, cash-flow chart, goals) is supporting detail. */}

      {core?.early_warning && core.early_warning.length > 0 && (
        <EarlyWarningBanner warnings={core.early_warning} />
      )}

      {core?.safe_to_spend && (
        <SafeToSpendHero
          data={core.safe_to_spend}
          onUpdated={(next: SafeToSpend) =>
            setCore((c) => (c ? { ...c, safe_to_spend: next } : c))
          }
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 sm:gap-5 mb-5">
        <div className="lg:col-span-3 min-w-0">
          {core?.time_machine && (
            <TimeMachine
              data={core.time_machine}
              onChange={(next: TimeMachineData) =>
                setCore((c) => (c ? { ...c, time_machine: next } : c))
              }
            />
          )}
        </div>
        <div className="lg:col-span-2 min-w-0">
          {core?.next_best_action && (
            <NextBestActionCard
              data={core.next_best_action}
              onRefreshed={(next: NextBestAction) =>
                setCore((c) => (c ? { ...c, next_best_action: next } : c))
              }
            />
          )}
        </div>
      </div>

      {/* Hero row: Health Score gauge + key stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5 mb-5 sm:mb-6">
        <GlassCard strong className="edge-accent lg:col-span-1 flex flex-col items-center justify-center py-7">
          <HealthGauge score={score} />
          <p className="text-sm text-fog mt-3 font-medium">Financial Health Score</p>
          <a href="/twin" className="text-xs text-mint hover:underline mt-1">
            See what drives this
          </a>
        </GlassCard>

        <GlassCard className="lg:col-span-2 min-w-0">
          <p className="text-sm text-fog mb-4">6-Month Cash Flow</p>
          <div ref={chartRef} className="w-full h-[180px]">
            {chartW > 0 && (
              <AreaChart width={chartW} height={180} data={series}>
                <defs>
                  <linearGradient id="income" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={ct.mint} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={ct.mint} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="expense" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={ct.rose} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={ct.rose} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={ct.grid} vertical={false} />
                <XAxis dataKey="month" stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false}
                  tickFormatter={(v) => formatINR(v, { compact: true })} />
                <Tooltip
                  contentStyle={tooltipStyle(ct)}
                  formatter={(v: number) => formatINR(v)}
                />
                <Area type="monotone" dataKey="income" stroke={ct.mint} fill="url(#income)" strokeWidth={2} />
                <Area type="monotone" dataKey="expense" stroke={ct.rose} fill="url(#expense)" strokeWidth={2} />
              </AreaChart>
            )}
          </div>
        </GlassCard>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-5 sm:mb-6">
        <StatCard label="Net Worth" value={formatINR(snapshot.net_worth)} tint="violet" icon={<Sparkle size={15} className="text-violet" />} />
        <StatCard
          label="Savings Rate"
          tint="mint"
          value={`${snapshot.savings_rate}%`}
          icon={snapshot.savings_rate >= 20 ? <TrendingUp size={15} className="text-mint" /> : <TrendingDown size={15} className="text-rose" />}
        />
        <StatCard
          label="Monthly Cash Flow"
          tint={cashFlowPositive ? "mint" : "rose"}
          value={formatINR(snapshot.cash_flow)}
          accent={cashFlowPositive ? "text-mint" : "text-rose"}
        />
        <StatCard label="Total Liabilities" value={formatINR(snapshot.total_liabilities)} tint="rose" accent="text-rose" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5">
        {/* Goal Progress */}
        <GlassCard>
          <p className="text-sm text-fog mb-4">Goal Progress</p>
          <div className="space-y-4">
            {goals.length === 0 && (
              <p className="text-sm text-mist">No goals yet — set one to get a timeline.</p>
            )}
            {goals.map((g) => {
              const pct = Math.min((g.current_amount / g.target_amount) * 100, 100);
              return (
                <div key={g.id}>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-white truncate">{g.name}</span>
                    <span className="ledger text-fog shrink-0 ml-2">{formatINR(g.current_amount, { compact: true })} / {formatINR(g.target_amount, { compact: true })}</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/[0.07] border border-line/60 overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-mint to-violet" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>

        {/* Recent Insights / Upcoming Risks */}
        <GlassCard>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-fog">More opportunities</p>
            <a href="/insights" className="text-xs text-mint hover:underline">See all</a>
          </div>
          <div className="space-y-3">
            {insights.map((ins, i) => (
              <div key={i} className="flex gap-3 items-start p-3 rounded-xl bg-white/[0.03] border border-line transition-colors hover:border-mint/30">
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

function StatCard({
  label, value, icon, accent, tint = "mint",
}: {
  label: string; value: string; icon?: React.ReactNode;
  accent?: string; tint?: "mint" | "violet" | "gold" | "rose";
}) {
  // A faint tinted wash per metric. In light mode four flat white cards in a
  // row read as a spreadsheet; the tint gives each one an identity without
  // resorting to heavy colour.
  const washes = {
    mint: "from-mint/[0.09] to-transparent",
    violet: "from-violet/[0.09] to-transparent",
    gold: "from-gold/[0.09] to-transparent",
    rose: "from-rose/[0.09] to-transparent",
  } as const;

  return (
    <GlassCard hover className={`!p-4 bg-gradient-to-br ${washes[tint]}`}>
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-xs text-mist truncate">{label}</span>
        <span className="shrink-0">{icon}</span>
      </div>
      <p className={`ledger text-lg sm:text-xl font-semibold truncate ${accent || "text-white"}`}>
        {value}
      </p>
    </GlassCard>
  );
}

function HealthGauge({ score }: { score: number }) {
  const ct = useChartTheme();
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 70 ? ct.mint : score >= 40 ? ct.gold : ct.rose;

  return (
    <svg width="160" height="160" viewBox="0 0 160 160">
      <circle cx="80" cy="80" r={radius} stroke={ct.grid} strokeWidth="10" fill="none" />
      <circle
        cx="80" cy="80" r={radius}
        stroke={color} strokeWidth="10" fill="none"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 80 80)"
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
      <text x="80" y="76" textAnchor="middle" className="ledger" fontSize="32" fill={ct.text} fontWeight="600">
        {score}
      </text>
      <text x="80" y="98" textAnchor="middle" fontSize="11" fill={ct.axis}>
        / 100
      </text>
    </svg>
  );
}
