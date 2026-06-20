"use client";

import { useEffect, useState } from "react";
import { Clock, BookOpen, Repeat2 } from "lucide-react";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { api } from "@/lib/api";

const TYPE_META: Record<string, { icon: any; color: string; label: string; desc: string }> = {
  episodic: { icon: Clock, color: "text-mint", label: "Episodic", desc: "Specific events & transactions" },
  semantic: { icon: BookOpen, color: "text-violet", label: "Semantic", desc: "Durable facts & preferences" },
  behavioral: { icon: Repeat2, color: "text-gold", label: "Behavioral", desc: "Detected patterns over time" },
};

export default function MemoryPage() {
  const [memories, setMemories] = useState<any[]>([]);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    api.getMemoryTimeline().then(setMemories).catch(() => {});
  }, []);

  const filtered = filter === "all" ? memories : memories.filter((m) => m.memory_type === filter);

  return (
    <div>
      <PageHeader title="Memory Timeline" subtitle="What FinMate remembers about you — and why it matters." />

      <div className="flex gap-2 mb-6">
        {["all", "episodic", "semantic", "behavioral"].map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`text-xs px-3 py-1.5 rounded-full border capitalize ${
              filter === t ? "border-mint/50 bg-mint/10 text-white" : "border-line text-fog"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="relative pl-6 border-l border-line space-y-4">
        {filtered.map((m) => {
          const meta = TYPE_META[m.memory_type] || TYPE_META.episodic;
          const Icon = meta.icon;
          return (
            <div key={m.id} className="relative">
              <div className={`absolute -left-[29px] top-1 w-3 h-3 rounded-full bg-ink border-2 border-line`} />
              <GlassCard className="!p-4">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <Icon size={13} className={meta.color} />
                    <span className={`text-xs font-medium ${meta.color}`}>{meta.label}</span>
                  </div>
                  <span className="text-xs text-mist ledger">
                    {new Date(m.created_at).toLocaleDateString("en-IN")}
                  </span>
                </div>
                <p className="text-sm text-white">{m.content}</p>
                <div className="mt-2 h-1 w-full rounded-full bg-line overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-mint to-violet" style={{ width: `${m.importance * 100}%` }} />
                </div>
              </GlassCard>
            </div>
          );
        })}
        {filtered.length === 0 && <p className="text-sm text-mist">No memories of this type yet.</p>}
      </div>
    </div>
  );
}
