"use client";

/**
 * Plan a Wedding.
 *
 * A themed flow over the existing goal planner, not a second planner. What
 * makes it worth its own page is the contributor model: weddings in India are
 * rarely funded by one person, and a single "monthly contribution" field
 * cannot represent self, parents and in-laws each committing an amount.
 *
 * The goal's monthly contribution is kept equal to the sum of the line items
 * by the API, so every projection elsewhere stays consistent with what is
 * pledged here.
 */
import { useEffect, useState } from "react";
import { Heart, UserPlus, Trash2, CalendarDays, TrendingUp } from "lucide-react";
import { GlassCard, PageHeader, StatRow } from "@/components/GlassCard";
import { LoadingState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatINR, formatDate } from "@/lib/api";
import type { Goal, ContributorView } from "@/lib/types";

const RELATIONSHIPS = ["self", "partner", "parents", "in-laws", "family"];

const BLANK_CONTRIB = {
  name: "", relationship_label: "parents", monthly_amount: 0,
  committed_lump_sum: 0, contributed_so_far: 0,
};

export default function WeddingPage() {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [view, setView] = useState<ContributorView | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState({
    name: "Our Wedding", target_amount: 1500000, current_amount: 0, target_date: "",
  });
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ ...BLANK_CONTRIB });
  const toast = useToast();

  async function load() {
    try {
      const goals = await api.getGoals();
      const wedding = goals.find((g) => g.goal_type === "wedding") ?? null;
      setGoal(wedding);
      setView(wedding ? await api.getContributors(wedding.id) : null);
    } catch (err) {
      toast.fromError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createGoal(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createGoal({
        name: creating.name || "Our Wedding",
        goal_type: "wedding",
        target_amount: Number(creating.target_amount),
        current_amount: Number(creating.current_amount) || 0,
        priority: 1,
        ...(creating.target_date
          ? { target_date: new Date(creating.target_date).toISOString() }
          : {}),
      });
      toast.success("Wedding goal created");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  async function addContributor(e: React.FormEvent) {
    e.preventDefault();
    if (!goal || !form.name.trim()) {
      toast.error("Give the contributor a name.");
      return;
    }
    try {
      await api.addContributor(goal.id, {
        ...form,
        monthly_amount: Number(form.monthly_amount) || 0,
        committed_lump_sum: Number(form.committed_lump_sum) || 0,
        contributed_so_far: Number(form.contributed_so_far) || 0,
      });
      setForm({ ...BLANK_CONTRIB });
      setAdding(false);
      toast.success("Contributor added");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  async function remove(id: number) {
    if (!goal) return;
    try {
      await api.removeContributor(goal.id, id);
      toast.success("Removed");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  if (loading) return <LoadingState label="Loading your wedding plan…" />;

  // --- No wedding goal yet: the themed creation flow ---
  if (!goal) {
    return (
      <ErrorBoundary>
        <PageHeader
          title="Plan a Wedding"
          subtitle="Set the target and the date, then add everyone who is contributing."
        />
        <GlassCard strong className="edge-accent max-w-xl">
          <div className="text-3xl mb-3">💍</div>
          <form onSubmit={createGoal} className="space-y-3">
            <div>
              <label className="text-xs text-mist">What are you calling it?</label>
              <input
                value={creating.name}
                onChange={(e) => setCreating({ ...creating, name: e.target.value })}
                className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs text-mist">Total budget (₹)</label>
                <input
                  type="number" min={1} value={creating.target_amount}
                  onChange={(e) => setCreating({ ...creating, target_amount: Number(e.target.value) })}
                  className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
                />
              </div>
              <div>
                <label className="text-xs text-mist">Already saved (₹)</label>
                <input
                  type="number" min={0} value={creating.current_amount}
                  onChange={(e) => setCreating({ ...creating, current_amount: Number(e.target.value) })}
                  className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-mist">Wedding date</label>
              <input
                type="date" value={creating.target_date}
                onChange={(e) => setCreating({ ...creating, target_date: e.target.value })}
                className="mt-1 w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              />
              <p className="text-xs text-mist mt-1">
                Without a date the plan can show progress, but not whether you will get
                there in time.
              </p>
            </div>
            <button
              type="submit"
              className="w-full h-10 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent text-sm font-medium"
            >
              Start planning
            </button>
          </form>
        </GlassCard>
      </ErrorBoundary>
    );
  }

  const pledgedMonthly = view?.pledged_monthly ?? 0;
  const remaining = view?.goal.remaining ?? 0;
  const progress = goal.target_amount
    ? Math.min((goal.current_amount / goal.target_amount) * 100, 100)
    : 0;

  return (
    <ErrorBoundary>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <PageHeader
          title={goal.name}
          subtitle="Everyone contributing, and what that adds up to."
        />
        <button
          onClick={() => setAdding((a) => !a)}
          className="text-xs px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-1.5 shrink-0"
        >
          <UserPlus size={12} /> Add contributor
        </button>
      </div>

      <GlassCard strong className="edge-accent mb-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs text-mist mb-1">Still to raise</p>
            <p className="ledger text-3xl font-semibold text-gradient">
              {formatINR(remaining)}
            </p>
            <p className="text-xs text-mist mt-1">
              of {formatINR(goal.target_amount)}
              {goal.target_date ? ` · by ${formatDate(goal.target_date)}` : ""}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-mist mb-1">Pledged each month</p>
            <p className="ledger text-2xl text-mint">{formatINR(pledgedMonthly)}</p>
            {view?.months_to_target != null && (
              <p className="text-xs text-mist mt-1">
                fully funded in ~{view.months_to_target} months
              </p>
            )}
          </div>
        </div>

        <div className="h-2 rounded-full bg-white/[0.07] border border-line/60 overflow-hidden mt-4">
          <div
            className="h-full rounded-full bg-gradient-to-r from-mint to-violet"
            style={{ width: `${progress}%` }}
          />
        </div>
      </GlassCard>

      {adding && (
        <GlassCard className="mb-5">
          <form onSubmit={addContributor} className="grid gap-2 sm:grid-cols-5">
            <input
              placeholder="Name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="sm:col-span-2 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <select
              value={form.relationship_label}
              onChange={(e) => setForm({ ...form, relationship_label: e.target.value })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
            >
              {RELATIONSHIPS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <input
              type="number" min={0} placeholder="₹ / month"
              value={form.monthly_amount || ""}
              onChange={(e) => setForm({ ...form, monthly_amount: Number(e.target.value) })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <input
              type="number" min={0} placeholder="One-off ₹"
              value={form.committed_lump_sum || ""}
              onChange={(e) => setForm({ ...form, committed_lump_sum: Number(e.target.value) })}
              className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
            />
            <button
              type="submit"
              className="sm:col-span-5 text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent font-medium"
            >
              Add
            </button>
          </form>
        </GlassCard>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <GlassCard className="lg:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <Heart size={15} className="text-violet" />
            <p className="text-sm text-white font-medium">Who is contributing</p>
          </div>

          {!view?.contributors.length ? (
            <p className="text-sm text-mist py-3">
              No contributors yet. Add everyone who is putting money in — the plan below
              updates from their pledges.
            </p>
          ) : (
            view.contributors.map((c) => (
              <div key={c.id} className="py-3 border-b border-line last:border-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-white truncate">
                      {c.name}
                      <span className="text-xs text-mist ml-2">{c.relationship}</span>
                    </p>
                    <p className="text-xs text-mist">
                      {formatINR(c.monthly_amount)}/month
                      {c.committed_lump_sum > 0 &&
                        ` · ${formatINR(c.committed_lump_sum)} one-off`}
                      {c.contributed_so_far > 0 &&
                        ` · ${formatINR(c.contributed_so_far)} given`}
                    </p>
                    <div className="h-1.5 rounded-full bg-white/[0.07] overflow-hidden mt-2 max-w-[220px]">
                      <div
                        className="h-full rounded-full bg-violet"
                        style={{ width: `${Math.max(c.share_of_monthly, 2)}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="ledger text-sm text-white">{c.share_of_monthly}%</p>
                    <button
                      onClick={() => remove(c.id)}
                      aria-label={`Remove ${c.name}`}
                      className="text-mist hover:text-rose mt-1"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </GlassCard>

        <GlassCard>
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={15} className="text-mint" />
            <p className="text-sm text-white font-medium">The plan</p>
          </div>
          <StatRow label="Target" value={formatINR(goal.target_amount)} />
          <StatRow label="Saved" value={formatINR(goal.current_amount)} accent="text-mint" />
          <StatRow label="Remaining" value={formatINR(remaining)} accent="text-rose" />
          <StatRow label="Pledged monthly" value={formatINR(pledgedMonthly)} />
          <StatRow label="One-off pledges" value={formatINR(view?.pledged_lump_sum ?? 0)} />

          {view?.months_to_target != null ? (
            <p className="text-xs text-mist mt-3 pt-3 border-t border-line leading-relaxed">
              At {formatINR(pledgedMonthly)} a month, plus the one-off pledges, this is
              fully funded in about {view.months_to_target} months.
            </p>
          ) : (
            <p className="text-xs text-gold mt-3 pt-3 border-t border-line leading-relaxed">
              No monthly pledges yet, so there is no timeline to project.
            </p>
          )}

          <a
            href="/reports"
            className="text-xs text-mint hover:underline mt-3 inline-flex items-center gap-1"
          >
            <CalendarDays size={11} /> Generate the full Wedding Financial Plan
          </a>
        </GlassCard>
      </div>
    </ErrorBoundary>
  );
}
