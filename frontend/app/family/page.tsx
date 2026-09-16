"use client";

/**
 * Family Wealth - a household view built on explicit consent.
 *
 * Every figure here is shown only because someone granted it. Where a member
 * withheld something the UI says so rather than showing a zero, and the
 * combined total states when it is partial - a household number that quietly
 * omits a member is worse than one that admits it is incomplete.
 */
import { useEffect, useState } from "react";
import { Users, UserPlus, Trash2, Copy, Check, ShieldCheck } from "lucide-react";
import { GlassCard, PageHeader } from "@/components/GlassCard";
import { LoadingState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatINR } from "@/lib/api";
import type { FamilyView } from "@/lib/types";

const BLANK = {
  email: "", display_name: "", role: "viewer",
  share_net_worth: true, share_goals: true, share_transactions: false,
};

export default function FamilyPage() {
  const [view, setView] = useState<FamilyView | null>(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ ...BLANK });
  const [lastToken, setLastToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const toast = useToast();

  async function load() {
    try {
      setView(await api.getFamily());
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

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await api.inviteFamily(form);
      setLastToken(res.invite_token ?? null);
      setForm({ ...BLANK });
      setAdding(false);
      toast.success(res.message);
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  async function revoke(id: number) {
    try {
      await api.revokeFamily(id);
      toast.success("Access revoked");
      load();
    } catch (err) {
      toast.fromError(err);
    }
  }

  if (loading) return <LoadingState label="Loading your family view…" />;
  if (!view) return null;

  return (
    <ErrorBoundary>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <PageHeader
          title="Family Wealth"
          subtitle="One picture of the household — built only from what each person chose to share."
        />
        <button
          onClick={() => setAdding((a) => !a)}
          className="text-xs px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-1.5 shrink-0"
        >
          <UserPlus size={12} /> Invite someone
        </button>
      </div>

      {adding && (
        <GlassCard className="mb-5">
          <form onSubmit={invite} className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <input
                type="email" required placeholder="Their email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
              />
              <input
                placeholder="Name (e.g. Mum)" value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
              />
            </div>

            <div>
              <p className="text-xs text-mist mb-2">
                What they can see. Nothing is shared until they accept.
              </p>
              <div className="flex flex-wrap gap-3">
                {([
                  ["share_net_worth", "Net worth"],
                  ["share_goals", "Goals"],
                  ["share_transactions", "Transactions"],
                ] as const).map(([key, label]) => (
                  <label key={key} className="text-xs text-fog inline-flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form[key] as boolean}
                      onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
                      className="accent-mint"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            <button
              type="submit"
              className="text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent font-medium"
            >
              Send invite
            </button>
          </form>
        </GlassCard>
      )}

      {lastToken && (
        <GlassCard className="mb-5 border border-mint/25">
          <p className="text-sm text-white mb-1">Invite created</p>
          <p className="text-xs text-mist mb-2">
            Share this link. A real deployment emails it instead of showing it here.
          </p>
          <div className="flex items-center gap-2">
            <code className="text-xs text-fog bg-white/[0.04] border border-line rounded px-2 py-1 truncate flex-1">
              {typeof window !== "undefined" ? window.location.origin : ""}/family/accept?token={lastToken}
            </code>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(
                  `${window.location.origin}/family/accept?token=${lastToken}`
                );
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="text-xs px-2 py-1.5 rounded-lg border border-line text-fog hover:text-white shrink-0 inline-flex items-center gap-1"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </GlassCard>
      )}

      <div className="grid gap-4 md:grid-cols-3 mb-5">
        <GlassCard className="edge-accent">
          <p className="text-xs text-mist mb-1">Combined net worth</p>
          <p className="ledger text-2xl text-gradient">
            {formatINR(view.combined_net_worth)}
          </p>
          <p className="text-xs text-mist mt-1">{view.note}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">Combined monthly cash flow</p>
          <p className="ledger text-2xl text-mint">
            {formatINR(view.combined_monthly_cash_flow)}
          </p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-mist mb-1">People</p>
          <p className="ledger text-2xl text-white">{view.counted}</p>
          <p className="text-xs text-mist mt-1">
            {view.pending_invites} pending · {view.withheld} withheld
          </p>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="flex items-center gap-2 mb-3">
          <Users size={15} className="text-violet" />
          <p className="text-sm text-white font-medium">Household</p>
        </div>

        {view.members.map((m, i) => (
          <div key={m.link_id ?? `owner-${i}`} className="py-3 border-b border-line last:border-0">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm text-white">
                  {m.name}
                  {m.is_owner && <span className="text-xs text-mint ml-2">you</span>}
                  {m.status === "pending" && (
                    <span className="text-xs text-gold ml-2">invite pending</span>
                  )}
                </p>
                <p className="text-xs text-mist">{m.email}</p>

                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {Object.entries(m.shares).map(([k, on]) => (
                    <span
                      key={k}
                      className={`text-[10px] px-2 py-0.5 rounded-full border ${
                        on ? "border-mint/30 text-mint" : "border-line text-mist"
                      }`}
                    >
                      {k.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>

                {m.note && <p className="text-xs text-mist mt-1.5">{m.note}</p>}
              </div>

              <div className="text-right shrink-0">
                <p className="ledger text-sm text-white">
                  {m.net_worth != null ? formatINR(m.net_worth) : "—"}
                </p>
                {m.health_score != null && (
                  <p className="text-xs text-mist">score {m.health_score}</p>
                )}
                {!m.is_owner && m.link_id && (
                  <button
                    onClick={() => revoke(m.link_id!)}
                    aria-label="Revoke access"
                    className="text-mist hover:text-rose mt-1"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </div>

            {m.goals && m.goals.length > 0 && (
              <div className="mt-2 ml-1 space-y-1">
                {m.goals.slice(0, 3).map((g) => (
                  <div key={g.name} className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-mist truncate">{g.name}</span>
                    <span className="ledger text-mist shrink-0">{g.percent}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </GlassCard>

      <div className="flex items-start gap-2 mt-4 text-xs text-mist">
        <ShieldCheck size={13} className="text-mint mt-0.5 shrink-0" />
        <span>
          Members choose what to share and can be revoked at any time. A pending invite
          grants nothing.
        </span>
      </div>
    </ErrorBoundary>
  );
}
