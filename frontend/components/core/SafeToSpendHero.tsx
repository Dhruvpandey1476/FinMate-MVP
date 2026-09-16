"use client";

/**
 * Safe-to-Spend hero.
 *
 * This replaces raw balance as the most prominent number on the dashboard.
 * Two things it must never do:
 *
 *   1. Imply a live bank feed. There is no Account Aggregator, so the balance
 *      is labelled with its basis ("as of your last update") and the checkpoint
 *      prompt is always one tap away.
 *   2. Show a number without its reasoning. The breakdown expands to the exact
 *      bills, goals and buffer that were subtracted - a figure a user cannot
 *      interrogate is a figure they will not make a spending decision on.
 */
import { useState } from "react";
import { ChevronDown, Wallet, Pencil, Check, X, CalendarClock, Target, Shield } from "lucide-react";
import { GlassCard } from "@/components/GlassCard";
import { useToast } from "@/components/Toast";
import { api, formatINR, formatDate } from "@/lib/api";
import type { SafeToSpend } from "@/lib/types";

export default function SafeToSpendHero({
  data,
  onUpdated,
}: {
  data: SafeToSpend;
  onUpdated: (next: SafeToSpend) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const { deductions: d } = data;
  const negative = data.is_negative;

  async function saveCheckpoint(e: React.FormEvent) {
    e.preventDefault();
    const value = parseFloat(draft);
    if (!Number.isFinite(value) || value < 0) {
      toast.error("Enter your current account balance.");
      return;
    }
    setSaving(true);
    try {
      const res = await api.addBalanceCheckpoint(value);
      onUpdated(res.safe_to_spend);
      setEditing(false);
      setDraft("");
      toast.success("Balance updated");
    } catch (err) {
      toast.fromError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <GlassCard strong className="edge-accent mb-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Wallet size={14} className="text-mint shrink-0" />
            <p className="text-sm text-fog">Safe to spend today</p>
          </div>
          <p
            className={`ledger text-4xl sm:text-5xl font-semibold tracking-tight ${
              negative ? "text-rose" : "text-gradient"
            }`}
          >
            {formatINR(data.safe_to_spend)}
          </p>
          <p className="text-xs text-mist mt-2 max-w-md leading-relaxed">{data.summary}</p>
        </div>

        {/* Balance basis is stated plainly rather than implied. */}
        <div className="text-right shrink-0">
          <p className="text-xs text-mist mb-0.5">Balance</p>
          <p className="ledger text-lg text-white">{formatINR(data.balance.amount)}</p>
          <p className="text-[11px] text-mist max-w-[160px] leading-snug">
            {data.balance.label}
            {data.balance.as_of ? ` (${formatDate(data.balance.as_of)})` : ""}
          </p>
          <button
            onClick={() => {
              setEditing((v) => !v);
              setDraft(String(Math.round(data.balance.amount)));
            }}
            className="mt-1.5 text-xs text-mint hover:underline inline-flex items-center gap-1"
          >
            <Pencil size={11} /> Update balance
          </button>
        </div>
      </div>

      {editing && (
        <form
          onSubmit={saveCheckpoint}
          className="mt-4 pt-4 border-t border-line flex flex-wrap items-center gap-2"
        >
          <label className="text-xs text-mist w-full sm:w-auto">
            What does your account actually say right now?
          </label>
          <input
            type="number"
            inputMode="decimal"
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. 48500"
            className="flex-1 min-w-[140px] bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
          />
          <button
            type="submit"
            disabled={saving}
            className="text-xs px-3 py-2 rounded-lg bg-mint/15 border border-mint/30 text-mint inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <Check size={12} /> {saving ? "Saving…" : "Confirm"}
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-xs px-3 py-2 rounded-lg border border-line text-mist hover:text-white inline-flex items-center gap-1.5"
          >
            <X size={12} /> Cancel
          </button>
        </form>
      )}

      {data.needs_checkpoint && !editing && (
        <p className="mt-3 text-xs text-gold/90 bg-gold/10 border border-gold/20 rounded-lg px-3 py-2">
          {data.balance.basis === "checkpoint"
            ? `It's been ${data.balance.stale_days} days since you confirmed your balance — a quick update keeps this exact.`
            : "Confirm your real account balance to make this figure exact."}
        </p>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mt-4 text-xs text-mist hover:text-white inline-flex items-center gap-1.5 transition-colors"
      >
        <ChevronDown
          size={13}
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        />
        {open ? "Hide" : "Show"} how this is calculated
      </button>

      {open && (
        <div className="mt-3 pt-4 border-t border-line space-y-4 animate-in">
          <Row
            icon={<Wallet size={13} className="text-fog" />}
            label="Your balance"
            value={formatINR(data.balance.amount)}
            positive
          />

          <Breakdown
            icon={<CalendarClock size={13} className="text-rose" />}
            label={`Bills due in the next ${data.horizon_days} days`}
            total={d.upcoming_bills.total}
            rows={d.upcoming_bills.items.map((b) => ({
              name: b.label,
              meta: formatDate(b.due_date),
              amount: b.amount,
            }))}
            empty="No committed bills detected in this window."
          />

          <Breakdown
            icon={<Target size={13} className="text-violet" />}
            label="Still to set aside for goals this month"
            total={d.goal_contributions.total}
            rows={d.goal_contributions.items.map((g) => ({
              name: g.goal,
              meta: g.note ?? (g.already_set_aside
                ? `${formatINR(g.already_set_aside)} of ${formatINR(g.monthly_target ?? 0)} done`
                : undefined),
              amount: g.amount,
            }))}
            empty="No monthly goal contributions set."
          />

          <Row
            icon={<Shield size={13} className="text-gold" />}
            label="Safety buffer"
            value={`− ${formatINR(d.safety_buffer.total)}`}
            meta={d.safety_buffer.basis}
          />

          <div className="flex items-center justify-between pt-3 border-t border-line">
            <span className="text-sm text-white font-medium">Safe to spend</span>
            <span className={`ledger text-base font-semibold ${negative ? "text-rose" : "text-mint"}`}>
              {formatINR(data.safe_to_spend)}
            </span>
          </div>
        </div>
      )}
    </GlassCard>
  );
}

function Row({
  icon, label, value, meta, positive = false,
}: {
  icon: React.ReactNode; label: string; value: string; meta?: string; positive?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-2 min-w-0">
        <span className="mt-0.5 shrink-0">{icon}</span>
        <div className="min-w-0">
          <p className="text-sm text-white">{label}</p>
          {meta && <p className="text-xs text-mist leading-snug">{meta}</p>}
        </div>
      </div>
      <span className={`ledger text-sm shrink-0 ${positive ? "text-white" : "text-fog"}`}>
        {value}
      </span>
    </div>
  );
}

function Breakdown({
  icon, label, total, rows, empty,
}: {
  icon: React.ReactNode;
  label: string;
  total: number;
  rows: { name: string; meta?: string; amount: number }[];
  empty: string;
}) {
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <span className="mt-0.5 shrink-0">{icon}</span>
          <p className="text-sm text-white">{label}</p>
        </div>
        <span className="ledger text-sm text-fog shrink-0">− {formatINR(total)}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-mist mt-1 ml-5">{empty}</p>
      ) : (
        <div className="mt-1.5 ml-5 space-y-1">
          {rows.slice(0, 6).map((r, i) => (
            <div key={`${r.name}-${i}`} className="flex items-center justify-between gap-3 text-xs">
              <span className="text-mist truncate">
                {r.name}
                {r.meta && <span className="text-mist/70"> · {r.meta}</span>}
              </span>
              <span className="ledger text-mist shrink-0">{formatINR(r.amount)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
