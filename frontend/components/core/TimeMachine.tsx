"use client";

/**
 * Financial Time Machine.
 *
 * A friendlier front door to the existing scenario simulator: a horizon
 * switcher, plain-language framing, and an inline what-if that answers
 * "can I afford this?" without navigating away. The detailed scenario
 * breakdowns still live on /simulate.
 */
import { useState } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceDot, Legend,
} from "recharts";
import { Clock, Flag, Sparkles, X } from "lucide-react";
import { GlassCard } from "@/components/GlassCard";
import { ChartBox } from "@/components/ChartBox";
import { useToast } from "@/components/Toast";
import { useChartTheme, tooltipStyle } from "@/lib/chartTheme";
import { api, formatINR } from "@/lib/api";
import type { TimeMachine as TimeMachineData } from "@/lib/types";

const HORIZONS = [3, 6, 12, 24];

export default function TimeMachine({
  data,
  onChange,
}: {
  data: TimeMachineData;
  onChange: (next: TimeMachineData) => void;
}) {
  const ct = useChartTheme();
  const toast = useToast();
  const [months, setMonths] = useState(data.months);
  const [whatIf, setWhatIf] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(nextMonths: number, amount?: number) {
    setBusy(true);
    try {
      const next = amount
        ? await api.runTimeMachine({ months: nextMonths, what_if_amount: amount })
        : await api.getTimeMachine(nextMonths);
      setMonths(nextMonths);
      onChange(next);
    } catch (err) {
      toast.fromError(err);
    } finally {
      setBusy(false);
    }
  }

  async function runWhatIf(e: React.FormEvent) {
    e.preventDefault();
    const amount = parseFloat(whatIf);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error("Enter an amount to model.");
      return;
    }
    await load(months, amount);
  }

  const chartData = data.month_labels.map((label, i) => ({
    label,
    baseline: data.baseline_net_worth[i],
    projected: data.projected_net_worth[i],
    real: data.real_net_worth[i],
  }));

  const hasWhatIf = Boolean(data.what_if);

  return (
    <GlassCard className="mb-5">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Clock size={15} className="text-violet shrink-0" />
          <p className="text-sm text-fog">Financial Time Machine</p>
        </div>
        <div className="flex gap-1 shrink-0">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => load(h, data.what_if?.amount)}
              disabled={busy}
              className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors disabled:opacity-50 ${
                months === h
                  ? "border-violet/50 text-violet bg-violet/10"
                  : "border-line text-mist hover:text-white"
              }`}
            >
              {h}m
            </button>
          ))}
        </div>
      </div>

      <p className="text-base sm:text-lg text-white leading-snug mb-1 text-balance">
        {data.headline}
      </p>
      {typeof data.assumptions.run_rate_basis === "string" && (
        <p className="text-xs text-mist mb-4">
          Based on the {data.assumptions.run_rate_basis}.
        </p>
      )}

      <ChartBox height={220}>
        {(w) => (
          <ComposedChart data={chartData} width={w} height={220}
                         margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="tmFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={ct.violet} stopOpacity={0.28} />
                <stop offset="100%" stopColor={ct.violet} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={ct.grid} vertical={false} />
            <XAxis dataKey="label" stroke={ct.axis} fontSize={11} tickLine={false}
                   axisLine={false} minTickGap={28} />
            <YAxis stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false}
                   tickFormatter={(v) => formatINR(Number(v), { compact: true })} />
            <Tooltip contentStyle={tooltipStyle(ct)}
                     formatter={(v: number) => formatINR(v)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />

            <Area type="monotone" dataKey="baseline" stroke="none" fill="url(#tmFill)"
                  name="Current pace" legendType="none" />
            <Line type="monotone" dataKey="baseline" stroke={ct.violet} strokeWidth={2.5}
                  dot={false} name="Current pace" />
            {hasWhatIf && (
              <Line type="monotone" dataKey="projected" stroke={ct.gold} strokeWidth={2.5}
                    dot={false} name="With this purchase" />
            )}
            <Line type="monotone" dataKey="real" stroke={ct.axis} strokeWidth={1.5}
                  strokeDasharray="4 3" dot={false} name="In today's money" />

            {data.key_moments.map((m) => (
              <ReferenceDot
                key={`${m.title}-${m.month_index}`}
                x={chartData[m.month_index]?.label}
                y={data.baseline_net_worth[m.month_index]}
                r={4}
                fill={ct.mint}
                stroke={ct.tooltipBg}
                strokeWidth={2}
              />
            ))}
          </ComposedChart>
        )}
      </ChartBox>

      {data.key_moments.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {data.key_moments.slice(0, 4).map((m) => (
            <span
              key={`${m.title}-${m.month_index}`}
              className="text-xs px-2.5 py-1 rounded-full bg-mint/10 border border-mint/25 text-mint inline-flex items-center gap-1.5"
            >
              <Flag size={10} />
              {m.title} · {m.label}
            </span>
          ))}
        </div>
      )}

      {/* Inline what-if: answers the question without leaving the dashboard. */}
      <form onSubmit={runWhatIf} className="mt-4 pt-4 border-t border-line">
        <label className="text-xs text-mist block mb-2">
          What if I buy something big?
        </label>
        <div className="flex gap-2 flex-wrap">
          <input
            type="number"
            inputMode="decimal"
            value={whatIf}
            onChange={(e) => setWhatIf(e.target.value)}
            placeholder="e.g. 80000 for a laptop"
            className="flex-1 min-w-[160px] bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-violet/50"
          />
          <button
            type="submit"
            disabled={busy}
            className="text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <Sparkles size={13} />
            {busy ? "Running…" : "See the impact"}
          </button>
          {hasWhatIf && (
            <button
              type="button"
              onClick={() => {
                setWhatIf("");
                load(months);
              }}
              className="text-sm px-3 py-2 rounded-lg border border-line text-mist hover:text-white inline-flex items-center gap-1.5"
            >
              <X size={13} /> Clear
            </button>
          )}
        </div>

        {data.what_if && (
          <div className="mt-3 p-3 rounded-xl bg-gold/[0.07] border border-gold/25 animate-in">
            <div className="flex items-baseline justify-between gap-3 mb-1">
              <span className="text-sm text-white">
                Buying at {formatINR(data.what_if.amount)}
              </span>
              <span className="ledger text-sm text-rose shrink-0">
                {formatINR(data.what_if.delta_at_end)} by month {months}
              </span>
            </div>
            {data.what_if.true_cost !== undefined && (
              <p className="text-xs text-mist leading-relaxed">
                True cost {formatINR(data.what_if.true_cost)} — the price plus{" "}
                {formatINR(data.what_if.opportunity_cost ?? 0)} of growth it displaces.
              </p>
            )}
          </div>
        )}
      </form>
    </GlassCard>
  );
}
