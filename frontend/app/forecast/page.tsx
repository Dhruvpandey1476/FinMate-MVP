"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";
import {
  AlertTriangle, CalendarClock, Repeat, TrendingDown, TrendingUp, ShieldCheck,
} from "lucide-react";
import { GlassCard, PageHeader, StatRow } from "@/components/GlassCard";
import { LoadingState, EmptyState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { useChartTheme, tooltipStyle } from "@/lib/chartTheme";
import { api, formatINR, formatDate } from "@/lib/api";
import type { Forecast, BudgetCategory } from "@/lib/types";

const HORIZONS = [30, 60, 90, 180];

export default function ForecastPage() {
  const ct = useChartTheme();
  const [days, setDays] = useState(90);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [budget, setBudget] = useState<BudgetCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  // Recharts' ResponsiveContainer renders blank inside CSS grid, so the width
  // is measured from the real DOM (same approach as the dashboard).
  const [chartW, setChartW] = useState(0);
  const roRef = useRef<ResizeObserver | null>(null);
  const chartRef = useCallback((node: HTMLDivElement | null) => {
    roRef.current?.disconnect();
    roRef.current = null;
    if (node) {
      const ro = new ResizeObserver((entries) => setChartW(entries[0].contentRect.width));
      ro.observe(node);
      roRef.current = ro;
      setChartW(node.clientWidth);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([api.getForecast(days), api.getBudget()])
      .then(([f, b]) => {
        if (cancelled) return;
        setForecast(f);
        setBudget(b);
      })
      .catch((err) => !cancelled && toast.fromError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  if (loading && !forecast) return <LoadingState label="Projecting your cash flow…" />;

  if (!forecast) {
    return (
      <EmptyState
        title="No forecast yet"
        description="Upload a bank statement or add a few transactions and FinMate will project your balance forward."
      />
    );
  }

  const atRisk = forecast.runway_days !== null;
  const chartData = forecast.series.map((p) => ({
    date: p.date,
    balance: p.balance,
    label: formatDate(p.date),
  }));

  return (
    <ErrorBoundary>
      <div className="flex items-start justify-between flex-wrap gap-3">
        <PageHeader
          title="Cash-Flow Forecast"
          subtitle="Where your balance goes next — from your detected bills and spending pace."
        />
        <div className="flex gap-1">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => setDays(h)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                days === h
                  ? "border-mint/50 text-mint bg-mint/10"
                  : "border-line text-mist hover:text-white"
              }`}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      {/* Headline: the answer to "when do I run out?" */}
      <GlassCard
        strong
        className={`mb-5 border ${atRisk ? "border-rose/30" : "border-mint/20"}`}
      >
        <div className="flex items-start gap-3">
          {atRisk ? (
            <AlertTriangle size={20} className="text-rose mt-0.5 shrink-0" />
          ) : (
            <ShieldCheck size={20} className="text-mint mt-0.5 shrink-0" />
          )}
          <div className="flex-1">
            <p className="text-white font-medium mb-1">
              {atRisk
                ? `Cash runs out in ${forecast.runway_days} days`
                : "Your cash flow holds up"}
            </p>
            <p className="text-sm text-mist leading-relaxed">{forecast.summary}</p>
          </div>
        </div>
      </GlassCard>

      <div className="grid gap-4 md:grid-cols-4 mb-5">
        <GlassCard>
          <p className="text-xs text-mist mb-1">Opening balance</p>
          <p className="ledger text-xl text-white">{formatINR(forecast.opening_balance)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">Committed bills / mo</p>
          <p className="ledger text-xl text-rose">{formatINR(forecast.monthly_committed)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">Recurring income / mo</p>
          <p className="ledger text-xl text-mint">{formatINR(forecast.monthly_recurring_income)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">Projected surplus / mo</p>
          <p
            className={`ledger text-xl ${
              forecast.projected_monthly_surplus >= 0 ? "text-mint" : "text-rose"
            }`}
          >
            {formatINR(forecast.projected_monthly_surplus)}
          </p>
        </GlassCard>
      </div>

      <GlassCard className="mb-5">
        <p className="text-sm text-white font-medium mb-4">Projected balance</p>
        <div ref={chartRef} className="w-full">
          {chartW > 0 && (
            <AreaChart width={chartW} height={240} data={chartData}
                       margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
              <defs>
                <linearGradient id="balanceFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={ct.mint} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={ct.mint} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis
                dataKey="label" stroke={ct.axis} fontSize={11} tickLine={false}
                axisLine={false} minTickGap={40}
              />
              <YAxis
                stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false}
                tickFormatter={(v) => formatINR(Number(v), { compact: true })}
              />
              <Tooltip
                contentStyle={tooltipStyle(ct)}
                labelStyle={{ color: ct.axis }}
                formatter={(v: number) => [formatINR(v), "Balance"]}
              />
              {/* Zero line makes "goes negative" legible at a glance. */}
              <ReferenceLine y={0} stroke={ct.rose} strokeDasharray="3 3" />
              <Area
                type="monotone" dataKey="balance" stroke={ct.mint}
                strokeWidth={2} fill="url(#balanceFill)"
              />
            </AreaChart>
          )}
        </div>
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard>
          <div className="flex items-center gap-2 mb-3">
            <Repeat size={15} className="text-violet" />
            <p className="text-sm text-white font-medium">Detected recurring charges</p>
          </div>
          {forecast.recurring_expenses.length === 0 ? (
            <p className="text-sm text-mist py-3">
              No repeating charges detected yet — three occurrences of the same
              merchant are needed before FinMate calls something recurring.
            </p>
          ) : (
            <div className="space-y-0">
              {forecast.recurring_expenses.slice(0, 8).map((r) => (
                <div
                  key={`${r.label}-${r.next_due}`}
                  className="flex items-center justify-between py-2.5 border-b border-line last:border-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-white truncate">{r.label}</p>
                    <p className="text-xs text-mist">
                      {r.cadence} · next {formatDate(r.next_due)}
                    </p>
                  </div>
                  <div className="text-right shrink-0 ml-3">
                    <p className="ledger text-sm text-white">{formatINR(r.amount)}</p>
                    <p className="text-xs text-mist">
                      {formatINR(r.monthly_equivalent)}/mo
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-2 mb-3">
            <CalendarClock size={15} className="text-gold" />
            <p className="text-sm text-white font-medium">Next 30 days of bills</p>
          </div>
          {forecast.upcoming_bills.length === 0 ? (
            <p className="text-sm text-mist py-3">Nothing scheduled in the next 30 days.</p>
          ) : (
            <div className="space-y-0">
              {forecast.upcoming_bills.slice(0, 8).map((b, i) => (
                <StatRow
                  key={`${b.label}-${b.date}-${i}`}
                  label={`${b.label} · ${formatDate(b.date!)}`}
                  value={formatINR(Math.abs(b.amount))}
                  accent="text-rose"
                />
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      {budget.length > 0 && (
        <GlassCard className="mt-4">
          <p className="text-sm text-white font-medium mb-3">
            This month versus your usual pace
          </p>
          <div className="space-y-3">
            {budget.slice(0, 6).map((c) => {
              const over = c.over_by > 0;
              const pct = Math.min(c.pct_of_average, 200);
              return (
                <div key={c.category}>
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      {over ? (
                        <TrendingUp size={12} className="text-rose shrink-0" />
                      ) : (
                        <TrendingDown size={12} className="text-mint shrink-0" />
                      )}
                      <span className="text-sm text-white truncate">{c.category}</span>
                    </div>
                    <span className="ledger text-xs text-mist shrink-0 ml-2">
                      {formatINR(c.spent_mtd)} of ~{formatINR(c.monthly_average)}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
                    <div
                      className={`h-full rounded-full ${over ? "bg-rose" : "bg-mint"}`}
                      style={{ width: `${Math.max(pct / 2, 2)}%` }}
                    />
                  </div>
                  <p className="text-xs text-mist mt-1">
                    {over
                      ? `${formatINR(c.over_by)} ahead of pace · on track for ${formatINR(
                          c.projected_month_end
                        )} by month end`
                      : `Under pace · ${c.days_left} days left`}
                  </p>
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}
    </ErrorBoundary>
  );
}
