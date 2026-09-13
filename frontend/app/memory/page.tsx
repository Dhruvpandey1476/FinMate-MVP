"use client";

import { useEffect, useState } from "react";
import {
  Brain, Pin, PinOff, Pencil, Trash2, Check, X, Plus, EyeOff, Eye,
} from "lucide-react";
import { GlassCard, PageHeader } from "@/components/GlassCard";
import { LoadingState, EmptyState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatDate } from "@/lib/api";
import type { Memory } from "@/lib/types";

const TYPES = [
  { id: "all", label: "All" },
  { id: "semantic", label: "Facts" },
  { id: "behavioral", label: "Patterns" },
  { id: "episodic", label: "Events" },
];

const TYPE_COLOR: Record<string, string> = {
  semantic: "text-mint border-mint/30 bg-mint/10",
  behavioral: "text-violet border-violet/30 bg-violet/10",
  episodic: "text-gold border-gold/30 bg-gold/10",
};

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newType, setNewType] = useState("semantic");
  const toast = useToast();

  async function load() {
    setLoading(true);
    try {
      setMemories(await api.getMemoryTimeline());
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

  async function patch(id: number, data: Partial<Memory>, successMsg?: string) {
    // Optimistic: the twin should feel immediately responsive to a correction.
    const previous = memories;
    setMemories((ms) => ms.map((m) => (m.id === id ? { ...m, ...data } : m)));
    try {
      const updated = await api.updateMemory(id, data);
      setMemories((ms) => ms.map((m) => (m.id === id ? updated : m)));
      if (successMsg) toast.success(successMsg);
    } catch (err) {
      setMemories(previous);
      toast.fromError(err);
    }
  }

  async function remove(id: number) {
    const previous = memories;
    setMemories((ms) => ms.filter((m) => m.id !== id));
    try {
      await api.deleteMemory(id);
      toast.success("Forgotten");
    } catch (err) {
      setMemories(previous);
      toast.fromError(err);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (newContent.trim().length < 3) return;
    try {
      const mem = await api.createMemory({
        memory_type: newType, content: newContent.trim(), importance: 0.75,
      });
      setMemories((ms) => [mem, ...ms]);
      setNewContent("");
      setAdding(false);
      toast.success("FinMate will remember that");
    } catch (err) {
      toast.fromError(err);
    }
  }

  const shown = filter === "all" ? memories : memories.filter((m) => m.memory_type === filter);

  return (
    <ErrorBoundary>
      <div className="flex items-start justify-between flex-wrap gap-3">
        <PageHeader
          title="Memory Timeline"
          subtitle="What your twin believes about you — correct anything it got wrong."
        />
        <button
          onClick={() => setAdding((a) => !a)}
          className="text-xs px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-1.5"
        >
          <Plus size={12} /> Teach FinMate
        </button>
      </div>

      {adding && (
        <GlassCard className="mb-4">
          <form onSubmit={create} className="space-y-3">
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder="e.g. I support my parents and send them ₹15,000 every month."
              className="w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50 resize-none"
            />
            <div className="flex items-center gap-2">
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50"
              >
                <option value="semantic">Fact about me</option>
                <option value="behavioral">A pattern</option>
                <option value="episodic">An event</option>
              </select>
              <button
                type="submit"
                disabled={newContent.trim().length < 3}
                className="text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-ink font-medium disabled:opacity-40"
              >
                Remember this
              </button>
            </div>
          </form>
        </GlassCard>
      )}

      <div className="flex gap-1 mb-4 flex-wrap">
        {TYPES.map((t) => (
          <button
            key={t.id}
            onClick={() => setFilter(t.id)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              filter === t.id
                ? "border-mint/50 text-mint bg-mint/10"
                : "border-line text-mist hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingState label="Loading memories…" />
      ) : shown.length === 0 ? (
        <EmptyState
          title="Nothing remembered yet"
          description="As you chat and upload statements, FinMate builds a picture of your finances here. You can also teach it something directly."
        />
      ) : (
        <div className="space-y-2">
          {shown.map((m) => (
            <GlassCard key={m.id} className={m.muted ? "opacity-50" : ""}>
              <div className="flex items-start gap-3">
                <Brain size={15} className="text-mist mt-1 shrink-0" />

                <div className="flex-1 min-w-0">
                  {editingId === m.id ? (
                    <div className="space-y-2">
                      <textarea
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={2}
                        maxLength={2000}
                        className="w-full bg-white/[0.04] border border-line rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-mint/50 resize-none"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            patch(m.id, { content: draft.trim() }, "Memory corrected");
                            setEditingId(null);
                          }}
                          disabled={draft.trim().length < 3}
                          className="text-xs px-3 py-1.5 rounded-lg bg-mint/15 border border-mint/30 text-mint inline-flex items-center gap-1.5 disabled:opacity-40"
                        >
                          <Check size={12} /> Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="text-xs px-3 py-1.5 rounded-lg border border-line text-mist hover:text-white inline-flex items-center gap-1.5"
                        >
                          <X size={12} /> Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm text-white leading-relaxed">{m.content}</p>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-full border capitalize ${
                            TYPE_COLOR[m.memory_type] ?? "text-mist border-line"
                          }`}
                        >
                          {m.memory_type}
                        </span>
                        <span className="text-xs text-mist">{formatDate(m.created_at)}</span>
                        {m.source !== "system" && (
                          <span className="text-xs text-mist">· from {m.source}</span>
                        )}
                        {m.pinned && (
                          <span className="text-xs text-mint inline-flex items-center gap-1">
                            <Pin size={10} /> always considered
                          </span>
                        )}
                        {m.muted && <span className="text-xs text-mist">· ignored</span>}
                      </div>
                    </>
                  )}
                </div>

                {editingId !== m.id && (
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => patch(m.id, { pinned: !m.pinned })}
                      title={m.pinned ? "Unpin" : "Always consider this"}
                      className={`p-1.5 rounded-lg transition-colors ${
                        m.pinned ? "text-mint" : "text-mist hover:text-white"
                      }`}
                    >
                      {m.pinned ? <PinOff size={13} /> : <Pin size={13} />}
                    </button>
                    <button
                      onClick={() => patch(m.id, { muted: !m.muted })}
                      title={m.muted ? "Use this again" : "Ignore this"}
                      className="p-1.5 rounded-lg text-mist hover:text-white transition-colors"
                    >
                      {m.muted ? <Eye size={13} /> : <EyeOff size={13} />}
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(m.id);
                        setDraft(m.content);
                      }}
                      title="Correct this"
                      className="p-1.5 rounded-lg text-mist hover:text-white transition-colors"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => remove(m.id)}
                      title="Forget permanently"
                      className="p-1.5 rounded-lg text-mist hover:text-rose transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                )}
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </ErrorBoundary>
  );
}
