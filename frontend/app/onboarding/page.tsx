"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, Plus, Trash2 } from "lucide-react";
import { GlassCard } from "@/components/GlassCard";
import { api } from "@/lib/api";

const CATEGORIES = ["Rent", "Groceries", "Food Delivery", "Transport", "Utilities",
  "Entertainment", "Shopping", "Subscriptions", "EMI/Loan", "Other"];

export default function Onboarding() {
  const router = useRouter();
  const [income, setIncome] = useState("");
  const [expenses, setExpenses] = useState([
    { category: "Rent", amount: "" },
    { category: "Food Delivery", amount: "" },
  ]);
  const [goalName, setGoalName] = useState("");
  const [goalTarget, setGoalTarget] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function setExp(i: number, key: "category" | "amount", v: string) {
    setExpenses((xs) => xs.map((x, idx) => (idx === i ? { ...x, [key]: v } : x)));
  }
  const addRow = () => setExpenses((xs) => [...xs, { category: "Other", amount: "" }]);
  const removeRow = (i: number) => setExpenses((xs) => xs.filter((_, idx) => idx !== i));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!income || parseFloat(income) <= 0) {
      setError("Please enter your monthly income to continue.");
      return;
    }
    setSaving(true);
    try {
      await api.onboard({
        monthly_income: parseFloat(income),
        expenses: expenses
          .filter((x) => x.amount && parseFloat(x.amount) > 0)
          .map((x) => ({ category: x.category, amount: parseFloat(x.amount) })),
        goal: goalName && goalTarget ? { name: goalName, target_amount: parseFloat(goalTarget) } : null,
        note: note.trim() || null,
      });
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Something went wrong");
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-mint to-violet flex items-center justify-center shadow-glow">
          <Sparkles size={14} className="text-ink" />
        </div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Quick setup</h1>
      </div>
      <p className="text-sm text-mist mb-6">
        Takes 30 seconds. No bank statement needed — just a few numbers so your AI CFO
        can give real, personalized advice. You can refine anytime.
      </p>

      <form onSubmit={submit} className="space-y-5">
        <GlassCard>
          <label className="text-sm text-white font-medium">Monthly income (₹)</label>
          <input
            type="number" value={income} onChange={(e) => setIncome(e.target.value)}
            placeholder="e.g. 80000"
            className="mt-2 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-mint/50"
          />
        </GlassCard>

        <GlassCard>
          <div className="flex items-center justify-between mb-3">
            <label className="text-sm text-white font-medium">Top monthly expenses</label>
            <button type="button" onClick={addRow} className="text-xs text-mint flex items-center gap-1">
              <Plus size={13} /> Add
            </button>
          </div>
          <div className="space-y-2">
            {expenses.map((x, i) => (
              <div key={i} className="flex gap-2">
                <select
                  value={x.category} onChange={(e) => setExp(i, "category", e.target.value)}
                  className="flex-1 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
                >
                  {CATEGORIES.map((c) => <option key={c} value={c} className="bg-ink">{c}</option>)}
                </select>
                <input
                  type="number" value={x.amount} onChange={(e) => setExp(i, "amount", e.target.value)}
                  placeholder="₹/month"
                  className="w-32 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
                />
                <button type="button" onClick={() => removeRow(i)} className="text-mist hover:text-rose px-1">
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard>
          <label className="text-sm text-white font-medium">A goal you're working toward (optional)</label>
          <div className="flex gap-2 mt-2">
            <input
              value={goalName} onChange={(e) => setGoalName(e.target.value)}
              placeholder="e.g. Emergency Fund"
              className="flex-1 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
            />
            <input
              type="number" value={goalTarget} onChange={(e) => setGoalTarget(e.target.value)}
              placeholder="Target ₹"
              className="w-36 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
            />
          </div>
        </GlassCard>

        <GlassCard>
          <label className="text-sm text-white font-medium">Anything else the CFO should remember? (optional)</label>
          <textarea
            value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. I prefer low-risk investments and want to buy a car next year."
            rows={2}
            className="mt-2 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50 resize-none"
          />
        </GlassCard>

        {error && <p className="text-sm text-rose">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="submit" disabled={saving}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-mint to-violet text-ink font-medium text-sm disabled:opacity-60"
          >
            {saving ? "Setting up…" : "Build my Financial Twin"}
          </button>
          <button type="button" onClick={() => router.push("/")} className="text-sm text-mist hover:text-white">
            Skip for now
          </button>
        </div>
      </form>
    </div>
  );
}
