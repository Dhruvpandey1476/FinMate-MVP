"use client";

import { useEffect, useState } from "react";
import { Plus, Target } from "lucide-react";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { api, formatINR } from "@/lib/api";

const GOAL_TYPES = ["emergency_fund", "vehicle", "home", "education", "startup", "custom"];

export default function GoalsPage() {
  const [goals, setGoals] = useState<any[]>([]);
  const [plan, setPlan] = useState<any>(null);
  const [activeGoal, setActiveGoal] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", goal_type: "custom", target_amount: "", monthly_contribution: "" });

  function loadGoals() {
    api.getGoals().then(setGoals).catch(() => {});
  }

  useEffect(() => { loadGoals(); }, []);

  function viewPlan(goalId: number) {
    setActiveGoal(goalId);
    api.getGoalPlan(goalId).then(setPlan).catch(() => {});
  }

  async function createGoal(e: React.FormEvent) {
    e.preventDefault();
    await api.createGoal({
      name: form.name,
      goal_type: form.goal_type,
      target_amount: parseFloat(form.target_amount),
      monthly_contribution: parseFloat(form.monthly_contribution || "0"),
    });
    setForm({ name: "", goal_type: "custom", target_amount: "", monthly_contribution: "" });
    setShowForm(false);
    loadGoals();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <PageHeader title="Goals" subtitle="Emergency fund, vehicle, home, education, startup — tracked and planned." />
        <button
          onClick={() => setShowForm((s) => !s)}
          className="h-10 px-4 rounded-xl bg-gradient-to-br from-mint to-violet text-ink text-sm font-medium flex items-center gap-1.5"
        >
          <Plus size={16} /> New Goal
        </button>
      </div>

      {showForm && (
        <GlassCard className="mb-6">
          <form onSubmit={createGoal} className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <input required placeholder="Goal name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50" />
            <select value={form.goal_type} onChange={(e) => setForm({ ...form, goal_type: e.target.value })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50">
              {GOAL_TYPES.map((t) => <option key={t} value={t} className="bg-panel">{t.replace("_", " ")}</option>)}
            </select>
            <input required type="number" placeholder="Target amount (₹)" value={form.target_amount}
              onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50" />
            <input type="number" placeholder="Monthly contribution (₹)" value={form.monthly_contribution}
              onChange={(e) => setForm({ ...form, monthly_contribution: e.target.value })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50" />
            <button type="submit" className="md:col-span-4 h-10 rounded-lg bg-white/[0.06] border border-line text-sm text-white hover:border-mint/50">
              Create Goal
            </button>
          </form>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="space-y-4">
          {goals.map((g) => {
            const pct = Math.min((g.current_amount / g.target_amount) * 100, 100);
            return (
              <GlassCard key={g.id} className={`cursor-pointer transition-colors ${activeGoal === g.id ? "border-mint/40" : ""}`}
                          
              >
                <div onClick={() => viewPlan(g.id)}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Target size={15} className="text-violet" />
                      <span className="text-white font-medium text-sm">{g.name}</span>
                    </div>
                    <span className="text-xs text-mist uppercase tracking-wide">P{g.priority}</span>
                  </div>
                  <div className="h-2 rounded-full bg-line overflow-hidden mb-2">
                    <div className="h-full rounded-full bg-gradient-to-r from-mint to-violet" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="ledger text-fog">{formatINR(g.current_amount)} / {formatINR(g.target_amount)}</span>
                    <span className="text-mist">{pct.toFixed(0)}% funded</span>
                  </div>
                </div>
              </GlassCard>
            );
          })}
          {goals.length === 0 && <p className="text-sm text-mist">No goals yet — create one above.</p>}
        </div>

        <GlassCard strong>
          <p className="text-sm text-fog mb-3">AI-Generated Plan</p>
          {!plan && <p className="text-sm text-mist">Click a goal to see its funding plan and milestones.</p>}
          {plan && !plan.error && (
            <div>
              <p className="text-sm text-white mb-4">{plan.recommendation}</p>
              <div className="grid grid-cols-2 gap-3 mb-4">
                <MiniStat label="Remaining" value={formatINR(plan.remaining_amount)} />
                <MiniStat label="Monthly Plan" value={formatINR(plan.recommended_monthly_contribution)} />
                <MiniStat label="Time to Goal" value={plan.months_to_complete ? `${plan.months_to_complete} mo` : "—"} />
                <MiniStat label="Milestones" value={`${plan.milestones?.length || 0}`} />
              </div>
              <div className="space-y-2">
                {plan.milestones?.map((m: any, i: number) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-mist w-14">Mo {m.month}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-line overflow-hidden">
                      <div className="h-full bg-mint" style={{ width: `${m.percent_complete}%` }} />
                    </div>
                    <span className="ledger text-xs text-fog w-12 text-right">{m.percent_complete}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white/[0.03] border border-line rounded-lg p-3">
      <p className="text-xs text-mist mb-1">{label}</p>
      <p className="ledger text-sm text-white font-medium">{value}</p>
    </div>
  );
}
