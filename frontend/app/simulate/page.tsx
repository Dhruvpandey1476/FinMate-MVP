"use client";

import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, Area, ComposedChart,
} from "recharts";
import { Info, Lock, Dices } from "lucide-react";
import { PageHeader, GlassCard, StatRow } from "@/components/GlassCard";
import { ChartBox } from "@/components/ChartBox";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { useChartTheme, tooltipStyle } from "@/lib/chartTheme";
import { api, formatINR } from "@/lib/api";
import type { SimulationResult, PlanSummary } from "@/lib/types";

const SCENARIOS = [
  { type: "purchase", label: "Purchase", field: "amount", fieldLabel: "Purchase amount (₹)" },
  { type: "salary_change", label: "Salary Change", field: "percent_change", fieldLabel: "% change (e.g. 20 or -10)" },
  { type: "investment", label: "Investment", field: "amount", fieldLabel: "Monthly investment (₹)" },
  { type: "savings", label: "Extra Savings", field: "amount", fieldLabel: "Extra monthly savings (₹)" },
  { type: "prepay_debt", label: "Prepay Debt", field: "amount", fieldLabel: "Lump sum toward a loan (₹)" },
] as const;

export default function SimulatePage() {
  const ct = useChartTheme();
  const [scenarioType, setScenarioType] = useState<string>("purchase");
  const [value, setValue] = useState("50000");
  const [months, setMonths] = useState(12);
  const [annualReturn, setAnnualReturn] = useState(10);
  const [inflation, setInflation] = useState(6);
  const [monteCarlo, setMonteCarlo] = useState(false);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState<PlanSummary | null>(null);
  const toast = useToast();

  useEffect(() => {
    api.getPlan().then(setPlan).catch(() => {});
  }, []);

  const current = SCENARIOS.find((s) => s.type === scenarioType)!;
  const mcAvailable = plan?.features?.monte_carlo ?? false;

  async function runSimulation(e: React.FormEvent) {
    e.preventDefault();
    const numeric = parseFloat(value);
    if (!Number.isFinite(numeric)) {
      toast.error("Enter a number to simulate.");
      return;
    }

    setLoading(true);
    try {
      const payload: Record<string, unknown> = {
        scenario_type: scenarioType,
        months_ahead: months,
        annual_return: annualReturn / 100,
        inflation: inflation / 100,
        monte_carlo: monteCarlo && mcAvailable,
      };
      if (current.field === "amount") payload.amount = numeric;
      if (current.field === "percent_change") payload.percent_change = numeric;

      setResult(await api.simulate(payload));
    } catch (err) {
      toast.fromError(err);
    } finally {
      setLoading(false);
    }
  }

  const chartData = result?.projected?.map((p, i) => ({
    month: p.month,
    projected: p.projected_net_worth,
    baseline: result.baseline[i]?.projected_net_worth,
    real: p.real_net_worth,
  }));

  const mc = result?.monte_carlo;

  return (
    <ErrorBoundary>
      <PageHeader
        title="Scenario Simulator"
        subtitle="What if you bought, invested, saved, or paid down debt differently?"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <GlassCard>
          <p className="text-sm text-fog mb-3">Run a scenario</p>
          <form onSubmit={runSimulation} className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {SCENARIOS.map((s) => (
                <button
                  type="button"
                  key={s.type}
                  onClick={() => setScenarioType(s.type)}
                  className={`text-xs py-2 rounded-lg border transition-colors ${
                    scenarioType === s.type
                      ? "border-mint/50 bg-mint/10 text-white"
                      : "border-line text-fog hover:text-white"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            <div>
              <label className="text-xs text-mist">{current.fieldLabel}</label>
              <input
                type="number" value={value} onChange={(e) => setValue(e.target.value)}
                className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              />
            </div>

            <div>
              <label className="text-xs text-mist">Months ahead</label>
              <input
                type="number" min={1} max={600} value={months}
                onChange={(e) => setMonths(parseInt(e.target.value || "12", 10))}
                className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              />
            </div>

            {/* Assumptions are explicit and editable - a projection that hides
                them is just a number the user has to take on faith. */}
            <div className="pt-3 border-t border-line space-y-3">
              <p className="text-xs text-mist font-medium">Assumptions</p>
              <div>
                <label className="text-xs text-mist flex justify-between">
                  <span>Annual return</span>
                  <span className="ledger text-white">{annualReturn}%</span>
                </label>
                <input
                  type="range" min={0} max={20} step={0.5} value={annualReturn}
                  onChange={(e) => setAnnualReturn(Number(e.target.value))}
                  className="w-full accent-mint mt-1"
                />
              </div>
              <div>
                <label className="text-xs text-mist flex justify-between">
                  <span>Inflation</span>
                  <span className="ledger text-white">{inflation}%</span>
                </label>
                <input
                  type="range" min={0} max={12} step={0.5} value={inflation}
                  onChange={(e) => setInflation(Number(e.target.value))}
                  className="w-full accent-violet mt-1"
                />
              </div>

              <label
                className={`flex items-center gap-2 text-xs ${
                  mcAvailable ? "text-fog cursor-pointer" : "text-mist cursor-not-allowed"
                }`}
                title={mcAvailable ? "" : "Available on Plus"}
              >
                <input
                  type="checkbox" checked={monteCarlo && mcAvailable} disabled={!mcAvailable}
                  onChange={(e) => setMonteCarlo(e.target.checked)}
                  className="accent-mint"
                />
                <Dices size={12} />
                Monte Carlo range
                {!mcAvailable && <Lock size={10} className="text-gold" />}
              </label>
            </div>

            <button
              type="submit" disabled={loading}
              className="w-full h-10 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent text-sm font-medium disabled:opacity-50"
            >
              {loading ? "Simulating…" : "Run Simulation"}
            </button>
          </form>
        </GlassCard>

        <GlassCard className="lg:col-span-2 min-w-0">
          <p className="text-sm text-fog mb-2">Projected Net Worth</p>

          {!result && <p className="text-sm text-mist">Run a scenario to see the projection.</p>}

          {result && (
            <>
              <p className="text-sm text-white mb-4 leading-relaxed">{result.summary}</p>

              <ChartBox height={260}>
                {(w) => (
                  <LineChart width={w} height={260} data={chartData}>
                    <CartesianGrid stroke={ct.grid} vertical={false} />
                    <XAxis
                      dataKey="month" stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false}
                      label={{ value: "Months ahead", position: "insideBottom", offset: -2, fill: ct.axis, fontSize: 11 }}
                    />
                    <YAxis
                      stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false}
                      tickFormatter={(v) => formatINR(Number(v), { compact: true })}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle(ct)}
                      formatter={(v: number) => formatINR(v)}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="baseline" stroke={ct.axis} strokeWidth={2} dot={false} name="Current trajectory" />
                    <Line type="monotone" dataKey="projected" stroke={ct.mint} strokeWidth={2.5} dot={false} name="With this scenario" />
                    <Line type="monotone" dataKey="real" stroke={ct.violet} strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="In today's money" />
                  </LineChart>
                )}
              </ChartBox>

              {mc && (
                <div className="mt-5 pt-4 border-t border-line">
                  <div className="flex items-center gap-2 mb-3">
                    <Dices size={14} className="text-violet" />
                    <p className="text-sm text-white font-medium">
                      Range of outcomes ({result.assumptions.monte_carlo_runs} simulations)
                    </p>
                  </div>

                  <ChartBox height={200}>
                    {(w) => (
                      <ComposedChart width={w} height={200} data={mc.bands}>
                        <CartesianGrid stroke={ct.grid} vertical={false} />
                        <XAxis dataKey="month" stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false} />
                        <YAxis
                          stroke={ct.axis} fontSize={11} tickLine={false} axisLine={false}
                          tickFormatter={(v) => formatINR(Number(v), { compact: true })}
                        />
                        <Tooltip
                          contentStyle={tooltipStyle(ct)}
                          formatter={(v: number) => formatINR(v)}
                        />
                        <Area type="monotone" dataKey="p90" stroke="none" fill={ct.violet} fillOpacity={0.14} name="Optimistic" />
                        <Area type="monotone" dataKey="p10" stroke="none" fill={ct.tooltipBg} fillOpacity={1} name="Pessimistic" />
                        <Line type="monotone" dataKey="p50" stroke={ct.violet} strokeWidth={2} dot={false} name="Median" />
                      </ComposedChart>
                    )}
                  </ChartBox>

                  <div className="grid grid-cols-3 gap-3 mt-3">
                    <div>
                      <p className="text-xs text-mist">Pessimistic (10%)</p>
                      <p className="ledger text-sm text-rose">{formatINR(mc.final_p10)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-mist">Median</p>
                      <p className="ledger text-sm text-white">{formatINR(mc.final_p50)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-mist">Optimistic (90%)</p>
                      <p className="ledger text-sm text-mint">{formatINR(mc.final_p90)}</p>
                    </div>
                  </div>
                </div>
              )}

              {result.scenario === "investment" && (
                <div className="mt-5 pt-4 border-t border-line space-y-1">
                  <StatRow label="Total contributed" value={formatINR(result.total_contributed ?? 0)} />
                  <StatRow label="Value before tax" value={formatINR(result.nominal_value ?? 0)} accent="text-mint" />
                  <StatRow label="Capital gains tax" value={formatINR(result.tax_paid ?? 0)} accent="text-rose" />
                  <StatRow label="After tax" value={formatINR(result.post_tax_value ?? 0)} accent="text-mint" />
                  <StatRow label="In today's money" value={formatINR(result.real_value_today ?? 0)} accent="text-violet" />
                </div>
              )}

              {result.scenario === "purchase" && (
                <div className="mt-5 pt-4 border-t border-line space-y-1">
                  <StatRow label="Sticker price" value={formatINR(result.one_time_amount ?? 0)} />
                  <StatRow label="Forgone growth" value={formatINR(result.opportunity_cost ?? 0)} accent="text-gold" />
                  <StatRow label="True cost" value={formatINR(result.true_cost ?? 0)} accent="text-rose" />
                </div>
              )}

              <div className="mt-4 flex items-start gap-2 text-xs text-mist pt-3 border-t border-line">
                <Info size={12} className="mt-0.5 shrink-0" />
                <span>{result.assumptions.note}</span>
              </div>
            </>
          )}
        </GlassCard>
      </div>
    </ErrorBoundary>
  );
}
