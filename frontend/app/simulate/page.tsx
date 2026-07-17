"use client";

import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { ChartBox } from "@/components/ChartBox";
import { api, formatINR } from "@/lib/api";

const SCENARIOS = [
  { type: "purchase", label: "Purchase", field: "amount", fieldLabel: "Purchase amount (₹)" },
  { type: "salary_change", label: "Salary Change", field: "percent_change", fieldLabel: "% change (e.g. 20 or -10)" },
  { type: "investment", label: "Investment", field: "amount", fieldLabel: "Monthly investment (₹)" },
  { type: "savings", label: "Extra Savings", field: "amount", fieldLabel: "Extra monthly savings (₹)" },
];

export default function SimulatePage() {
  const [scenarioType, setScenarioType] = useState("purchase");
  const [value, setValue] = useState("50000");
  const [months, setMonths] = useState(12);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const current = SCENARIOS.find((s) => s.type === scenarioType)!;

  async function runSimulation(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const payload: any = { scenario_type: scenarioType, months_ahead: months };
      if (current.field === "amount") payload.amount = parseFloat(value);
      if (current.field === "percent_change") payload.percent_change = parseFloat(value);
      const res = await api.simulate(payload);
      setResult(res);
    } finally {
      setLoading(false);
    }
  }

  const chartData = result?.projected?.map((p: any, i: number) => ({
    month: p.month,
    projected: p.projected_net_worth,
    baseline: result.baseline[i]?.projected_net_worth,
  }));

  return (
    <div>
      <PageHeader title="Scenario Simulator" subtitle="What if you bought, invested, saved, or earned differently?" />

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
                  className={`text-xs py-2 rounded-lg border ${
                    scenarioType === s.type ? "border-mint/50 bg-mint/10 text-white" : "border-line text-fog"
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
                type="number" value={months} onChange={(e) => setMonths(parseInt(e.target.value || "12"))}
                className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              />
            </div>
            <button type="submit" disabled={loading}
              className="w-full h-10 rounded-lg bg-gradient-to-br from-mint to-violet text-ink text-sm font-medium disabled:opacity-50">
              {loading ? "Simulating…" : "Run Simulation"}
            </button>
          </form>
        </GlassCard>

        <GlassCard className="lg:col-span-2 min-w-0">
          <p className="text-sm text-fog mb-2">Projected Net Worth</p>
          {!result && <p className="text-sm text-mist">Run a scenario to see the projection.</p>}
          {result && (
            <>
              <p className="text-sm text-white mb-4">{result.summary}</p>
              <ChartBox height={260}>
                {(w) => (
                  <LineChart width={w} height={260} data={chartData}>
                    <CartesianGrid stroke="#1E2740" vertical={false} />
                    <XAxis dataKey="month" stroke="#5E6A87" fontSize={11} tickLine={false} axisLine={false}
                      label={{ value: "Months ahead", position: "insideBottom", offset: -2, fill: "#5E6A87", fontSize: 11 }} />
                    <YAxis stroke="#5E6A87" fontSize={11} tickLine={false} axisLine={false}
                      tickFormatter={(v) => formatINR(v, { compact: true })} />
                    <Tooltip
                      contentStyle={{ background: "#11172A", border: "1px solid #1E2740", borderRadius: 12, fontSize: 12 }}
                      formatter={(v: number) => formatINR(v)}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="baseline" stroke="#5E6A87" strokeWidth={2} dot={false} name="Current trajectory" />
                    <Line type="monotone" dataKey="projected" stroke="#27E0A6" strokeWidth={2.5} dot={false} name="With this scenario" />
                  </LineChart>
                )}
              </ChartBox>
            </>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
