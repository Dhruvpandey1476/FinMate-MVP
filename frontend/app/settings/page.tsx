"use client";

import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Loader2, Zap, LogOut, Trash2 } from "lucide-react";
import { PageHeader, GlassCard, StatRow } from "@/components/GlassCard";
import { useToast } from "@/components/Toast";
import { api, formatINR, clearToken, apiBaseUrl } from "@/lib/api";
import type { PlanSummary } from "@/lib/types";

export default function SettingsPage() {
  const [user, setUser] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState<PlanSummary | null>(null);
  const toast = useToast();

  useEffect(() => {
    Promise.all([
      api.getUser().catch(() => null),
      api.getHealth().catch(() => null),
      api.getPlan().catch(() => null),
    ]).then(([u, h, p]) => {
      setUser(u);
      setHealth(h);
      setPlan(p as PlanSummary | null);
      setLoading(false);
    });
  }, []);

  const services = health?.services || {};
  const llm = health?.llm || {};

  return (
    <div>
      <PageHeader title="Settings" subtitle="System status, profile, and AI configuration." />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
        <GlassCard>
          <p className="text-sm text-fog mb-3">Profile</p>
          {user && (
            <div className="space-y-1">
              <StatRow label="Name" value={user.name} />
              <StatRow label="Email" value={user.email} />
              <StatRow label="Monthly Income" value={formatINR(user.monthly_income)} />
              <StatRow label="Risk Profile" value={user.risk_profile} accent="text-violet" />
            </div>
          )}
        </GlassCard>

        <GlassCard strong>
          <p className="text-sm text-fog mb-3">Infrastructure Status</p>
          {loading ? (
            <div className="flex items-center gap-2 text-mist">
              <Loader2 size={14} className="animate-spin" />
              <span className="text-sm">Checking services...</span>
            </div>
          ) : (
            <div className="space-y-3">
              <ServiceStatus
                name="PostgreSQL"
                description="Primary data store"
                connected={services.postgresql}
              />
              <ServiceStatus
                name="Qdrant Vector DB"
                description="Semantic memory search"
                connected={services.qdrant}
              />
              <ServiceStatus
                name="Neo4j Graph DB"
                description="Wealth knowledge graph"
                connected={services.neo4j}
              />
              <div className="pt-2 border-t border-line">
                <ServiceStatus
                  name={`LLM: ${llm.provider || "none"}`}
                  description={`Last used: ${llm.last_used || "none"}`}
                  connected={llm.configured}
                />
              </div>
            </div>
          )}
        </GlassCard>
      </div>

      <GlassCard>
        <p className="text-sm text-fog mb-3">AI Architecture</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="bg-white/[0.03] border border-line rounded-xl p-4">
            <p className="text-white font-medium mb-2">🤖 AI CFO Agent</p>
            <p className="text-xs text-mist leading-relaxed">
              LangGraph StateGraph with 4 nodes: Financial Analysis → Memory Retrieval → 
              Graph Reasoning → AI Synthesis. Uses Groq LLM for real-time responses.
            </p>
          </div>
          <div className="bg-white/[0.03] border border-line rounded-xl p-4">
            <p className="text-white font-medium mb-2">🧠 Memory Engine</p>
            <p className="text-xs text-mist leading-relaxed">
              Qdrant vector DB with Gemini text-embedding-004 for semantic memory retrieval.
              Episodic, semantic, and behavioral memory types.
            </p>
          </div>
          <div className="bg-white/[0.03] border border-line rounded-xl p-4">
            <p className="text-white font-medium mb-2">🕸️ Wealth Graph</p>
            <p className="text-xs text-mist leading-relaxed">
              Neo4j knowledge graph connecting Users, Goals, Assets, Liabilities, and 
              Spending Categories with DELAYS/BLOCKS relationships.
            </p>
          </div>
        </div>
      </GlassCard>


      {/* Build stamp: lets you tell a stale bundle from a failing API at a
          glance, which is otherwise guesswork on a deployed site. */}
      <GlassCard className="mb-6">
        <p className="text-sm text-white font-medium mb-3">Build</p>
        <div className="space-y-1">
          <StatRow label="Frontend commit" value={process.env.NEXT_PUBLIC_BUILD_SHA ?? "unknown"} />
          <StatRow
            label="Built at"
            value={
              process.env.NEXT_PUBLIC_BUILD_TIME
                ? new Date(process.env.NEXT_PUBLIC_BUILD_TIME).toLocaleString()
                : "unknown"
            }
          />
          <StatRow label="API endpoint" value={apiBaseUrl} />
        </div>
        <p className="text-xs text-mist mt-3 leading-relaxed">
          If the commit here isn&apos;t your latest push, the browser or CDN is serving an
          older bundle — hard-reload, or redeploy. NEXT_PUBLIC_* values are compiled in at
          build time, so changing them in a hosting dashboard needs a fresh deploy.
        </p>
      </GlassCard>

      {/* Plan, usage and the data controls DPDP compliance requires. */}
      <GlassCard className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={15} className="text-gold" />
          <p className="text-sm text-white font-medium">
            Plan &amp; usage{plan ? ` — ${plan.label}` : ""}
          </p>
        </div>

        {plan ? (
          <>
            <div className="space-y-1 mb-4">
              {Object.entries(plan.quotas).map(([kind, q]) => (
                <StatRow
                  key={kind}
                  label={kind === "chat" ? "AI CFO messages" : kind === "simulate" ? "Simulations" : "Statement uploads"}
                  value={q.limit < 0 ? "Unlimited" : `${q.used} / ${q.limit} this month`}
                  accent={q.limit >= 0 && q.remaining === 0 ? "text-rose" : "text-white"}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(plan.features).map(([name, on]) => (
                <span
                  key={name}
                  className={`text-[10px] px-2 py-0.5 rounded-full border capitalize ${
                    on ? "border-mint/30 text-mint bg-mint/10" : "border-line text-mist"
                  }`}
                >
                  {name.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-mist">Plan details unavailable.</p>
        )}

        <div className="flex flex-wrap gap-2 mt-5 pt-4 border-t border-line">
          <button
            onClick={async () => {
              try {
                await api.logoutAll();
                clearToken();
                window.location.href = "/login";
              } catch (err) {
                toast.fromError(err);
              }
            }}
            className="text-xs px-3 py-2 rounded-lg border border-line text-fog hover:text-white transition-colors inline-flex items-center gap-1.5"
          >
            <LogOut size={12} /> Sign out everywhere
          </button>
          <button
            onClick={async () => {
              if (!window.confirm("Permanently delete your account and all financial data? This cannot be undone.")) return;
              try {
                await api.deleteAccount();
                clearToken();
                window.location.href = "/login";
              } catch (err) {
                toast.fromError(err);
              }
            }}
            className="text-xs px-3 py-2 rounded-lg border border-rose/30 text-rose hover:bg-rose/10 transition-colors inline-flex items-center gap-1.5"
          >
            <Trash2 size={12} /> Delete account &amp; all data
          </button>
        </div>
      </GlassCard>
    </div>
  );
}

function ServiceStatus({
  name,
  description,
  connected,
}: {
  name: string;
  description: string;
  connected: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      {connected ? (
        <CheckCircle size={16} className="text-mint shrink-0" />
      ) : (
        <XCircle size={16} className="text-rose shrink-0" />
      )}
      <div className="flex-1">
        <p className="text-sm text-white">{name}</p>
        <p className="text-xs text-mist">{description}</p>
      </div>
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          connected
            ? "bg-mint/10 text-mint border border-mint/20"
            : "bg-rose/10 text-rose border border-rose/20"
        }`}
      >
        {connected ? "Connected" : "Offline"}
      </span>
    </div>
  );
}
