"use client";

import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Loader2 } from "lucide-react";
import { PageHeader, GlassCard, StatRow } from "@/components/GlassCard";
import { api, formatINR } from "@/lib/api";

export default function SettingsPage() {
  const [user, setUser] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getUser().catch(() => null),
      api.getHealth().catch(() => null),
    ]).then(([u, h]) => {
      setUser(u);
      setHealth(h);
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
