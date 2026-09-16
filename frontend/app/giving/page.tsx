"use client";

/**
 * Giving.
 *
 * A donations ledger that feeds the Tax-Ready Export. The 80G toggle is the
 * whole point and also the thing to be careful about: eligibility is a fact
 * about the receiving institution that FinMate cannot verify, so it is
 * recorded as something the user asserts, and the UI says so rather than
 * implying the flag was checked.
 */
import { useEffect, useState } from "react";
import { HandHeart, Plus, Trash2, Receipt, Info } from "lucide-react";
import { GlassCard, PageHeader } from "@/components/GlassCard";
import { LoadingState, EmptyState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatINR, formatDate } from "@/lib/api";
import type { DonationRow } from "@/lib/types";

const BLANK = {
  recipient: "", amount: 0, donated_on: "",
  is_80g_eligible: false, receipt_ref: "", note: "",
};

export default function GivingPage() {
  const [rows, setRows] = useState<DonationRow[]>([]);
  const [total, setTotal] = useState(0);
  const [eligible, setEligible] = useState(0);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ ...BLANK });
  const toast = useToast();

  async function load() {
    try {
      const data = await api.getDonations();
      setRows(data.donations);
      setTotal(data.total);
      setEligible(data.eligible_total);
      setNote(data.note);
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

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!form.recipient.trim() || Number(form.amount) <= 0) {
      toast.error("A recipient and an amount above zero are required.");
      return;
    }
    try {
      await api.addDonation({
        recipient: form.recipient.trim(),
        amount: Number(form.amount),
        is_80g_eligible: form.is_80g_eligible,
        receipt_ref: form.receipt_ref || null,
        note: form.note || null,
        ...(form.donated_on
          ? { donated_on: new Date(form.donated_on).toISOString() }
          : {}),
      });
      setForm({ ...BLANK });
      setAdding(false);
      toast.success("Donation logged");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteDonation(id);
      toast.success("Removed");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  if (loading) return <LoadingState label="Loading your giving…" />;

  return (
    <ErrorBoundary>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <PageHeader
          title="Giving"
          subtitle="What you gave, and which of it to gather receipts for at filing time."
        />
        <button
          onClick={() => setAdding((a) => !a)}
          className="text-xs px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-1.5 shrink-0"
        >
          <Plus size={12} /> Log a donation
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4 mb-5">
        <GlassCard className="edge-accent">
          <p className="text-xs text-mist mb-1">Given this year</p>
          <p className="ledger text-xl sm:text-2xl text-gradient truncate">
            {formatINR(total)}
          </p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">Marked 80G</p>
          <p className="ledger text-xl sm:text-2xl text-mint truncate">
            {formatINR(eligible)}
          </p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">Donations</p>
          <p className="ledger text-xl sm:text-2xl text-white">{rows.length}</p>
        </GlassCard>
      </div>

      {adding && (
        <GlassCard className="mb-5">
          <form onSubmit={add} className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-3">
              <input
                placeholder="Who did you give to?" value={form.recipient}
                onChange={(e) => setForm({ ...form, recipient: e.target.value })}
                className="sm:col-span-2 bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
              />
              <input
                type="number" min={1} placeholder="Amount ₹" value={form.amount || ""}
                onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <input
                type="date" value={form.donated_on}
                onChange={(e) => setForm({ ...form, donated_on: e.target.value })}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              />
              <input
                placeholder="Receipt reference" value={form.receipt_ref}
                onChange={(e) => setForm({ ...form, receipt_ref: e.target.value })}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
              />
              <input
                placeholder="Note (optional)" value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
              />
            </div>

            <label className="flex items-start gap-2 text-sm text-fog cursor-pointer">
              <input
                type="checkbox" checked={form.is_80g_eligible}
                onChange={(e) => setForm({ ...form, is_80g_eligible: e.target.checked })}
                className="accent-mint mt-0.5"
              />
              <span>
                My receipt says this institution is registered under 80G
                <span className="block text-xs text-mist">
                  FinMate records what you tell it here — it cannot check a registration.
                </span>
              </span>
            </label>

            <button
              type="submit"
              className="text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent font-medium"
            >
              Log it
            </button>
          </form>
        </GlassCard>
      )}

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing logged yet"
          description="Log what you give and FinMate keeps it together for filing time, flagged by whether your receipt says 80G."
        />
      ) : (
        <GlassCard>
          <div className="flex items-center gap-2 mb-3">
            <HandHeart size={15} className="text-violet" />
            <p className="text-sm text-white font-medium">Your donations</p>
          </div>

          {rows.map((d) => (
            <div key={d.id} className="flex items-start justify-between gap-3 py-2.5 border-b border-line last:border-0">
              <div className="min-w-0">
                <p className="text-sm text-white truncate">
                  {d.recipient}
                  {d.is_80g_eligible && (
                    <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-mint/15 border border-mint/30 text-mint">
                      80G
                    </span>
                  )}
                </p>
                <p className="text-xs text-mist">
                  {formatDate(d.donated_on)}
                  {d.receipt_ref && (
                    <span className="inline-flex items-center gap-1 ml-2">
                      <Receipt size={10} /> {d.receipt_ref}
                    </span>
                  )}
                </p>
                {d.note && <p className="text-xs text-mist mt-0.5">{d.note}</p>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="ledger text-sm text-white">{formatINR(d.amount)}</span>
                <button
                  onClick={() => remove(d.id)}
                  aria-label={`Delete donation to ${d.recipient}`}
                  className="text-mist hover:text-rose transition-colors"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </GlassCard>
      )}

      <div className="flex items-start gap-2 mt-4 text-xs text-mist">
        <Info size={13} className="mt-0.5 shrink-0" />
        <span>
          {note} These appear as their own section in the{" "}
          <a href="/reports" className="text-mint hover:underline">Tax-Ready Export</a>.
        </span>
      </div>
    </ErrorBoundary>
  );
}
