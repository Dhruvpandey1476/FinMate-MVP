"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Send, Brain, Zap, Square, Trash2 } from "lucide-react";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { useToast } from "@/components/Toast";
import { api, streamChat, ApiError } from "@/lib/api";
import type { ChatMessage, TraceStep, PlanSummary } from "@/lib/types";

const SUGGESTIONS = [
  "Can I afford a ₹50,000 laptop?",
  "Why am I overspending?",
  "When will I run out of money?",
  "Should I prepay my loan or invest?",
  "How close am I to financial freedom?",
  "What if I invest ₹10,000/month?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceStep[]>([]);
  const [plan, setPlan] = useState<PlanSummary | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const toast = useToast();

  useEffect(() => {
    api.getChatHistory().then(setMessages).catch((err) => {
      if (!(err instanceof ApiError && err.status === 401)) toast.fromError(err);
    });
    api.getPlan().then(setPlan).catch(() => {
      /* the meter is decoration; never block the chat over it */
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveTrace]);

  // Abort an in-flight stream if the user navigates away mid-answer.
  useEffect(() => () => abortRef.current?.(), []);

  const send = useCallback((text: string) => {
    const message = text.trim();
    if (!message || streaming) return;

    setMessages((m) => [
      ...m,
      { role: "user", content: message },
      { role: "assistant", content: "", streaming: true },
    ]);
    setInput("");
    setLiveTrace([]);
    setStreaming(true);

    abortRef.current = streamChat(message, {
      onTrace: (step) => setLiveTrace((t) => [...t, step]),
      onToken: (token) =>
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          if (last?.streaming) next[next.length - 1] = { ...last, content: last.content + token };
          return next;
        }),
      onDone: (reply, trace) => {
        setMessages((m) => {
          const next = [...m];
          next[next.length - 1] = {
            role: "assistant",
            content: reply,
            reasoning_trace: trace,
            streaming: false,
          };
          return next;
        });
        setLiveTrace([]);
        setStreaming(false);
        abortRef.current = null;
        // Keep the usage meter honest without a full refetch loop.
        setPlan((p) =>
          p && p.quotas.chat.limit >= 0
            ? {
                ...p,
                quotas: {
                  ...p.quotas,
                  chat: {
                    ...p.quotas.chat,
                    used: p.quotas.chat.used + 1,
                    remaining: Math.max(0, p.quotas.chat.remaining - 1),
                  },
                },
              }
            : p
        );
      },
      onError: (err) => {
        toast.fromError(err);
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          if (last?.streaming) {
            // Drop the empty placeholder rather than leaving a blank bubble.
            if (!last.content) next.pop();
            else next[next.length - 1] = { ...last, streaming: false };
          }
          return next;
        });
        setLiveTrace([]);
        setStreaming(false);
        abortRef.current = null;
      },
    });
  }, [streaming, toast]);

  function stop() {
    abortRef.current?.();
    abortRef.current = null;
    setStreaming(false);
    setMessages((m) => {
      const next = [...m];
      const last = next[next.length - 1];
      if (last?.streaming) {
        if (!last.content) next.pop();
        else next[next.length - 1] = { ...last, streaming: false };
      }
      return next;
    });
    setLiveTrace([]);
  }

  async function clearHistory() {
    try {
      await api.clearChatHistory();
      setMessages([]);
      toast.success("Conversation cleared");
    } catch (err) {
      toast.fromError(err);
    }
  }

  const chatQuota = plan?.quotas.chat;
  const quotaLow = chatQuota && chatQuota.limit >= 0 && chatQuota.remaining <= 5;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <PageHeader title="AI CFO Chat" subtitle="Ask anything about your money — powered by LangGraph agents." />
        <div className="flex items-center gap-2">
          {chatQuota && chatQuota.limit >= 0 && (
            <span
              className={`text-xs px-3 py-1.5 rounded-full border ${
                quotaLow ? "border-gold/30 text-gold bg-gold/10" : "border-line text-mist"
              }`}
            >
              {chatQuota.remaining} of {chatQuota.limit} left
            </span>
          )}
          <div className="flex items-center gap-1.5 text-xs text-mint bg-mint/10 px-3 py-1.5 rounded-full border border-mint/20">
            <Zap size={12} />
            AI-Powered
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearHistory}
              title="Clear conversation"
              className="p-2 rounded-lg border border-line text-mist hover:text-rose hover:border-rose/40 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      <GlassCard className="flex-1 flex flex-col overflow-hidden !p-0">
        <div className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-4">
          {messages.length === 0 && (
            <div>
              <p className="text-sm text-mist mb-3">Try asking:</p>
              <div className="flex flex-wrap gap-2 mb-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="text-xs px-3 py-1.5 rounded-full border border-line text-fog hover:text-white hover:border-mint/50 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={m.id ?? i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] ${m.role === "user" ? "" : "w-full"}`}>
                <div
                  className={`rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-gradient-to-br from-mint/20 to-violet/20 border border-mint/20 text-white"
                      : "glass text-white"
                  }`}
                >
                  {m.content}
                  {m.streaming && m.content && (
                    <span className="inline-block w-1.5 h-4 ml-0.5 bg-mint/70 align-text-bottom animate-pulse" />
                  )}
                </div>

                {m.reasoning_trace && m.reasoning_trace.length > 0 && (
                  <details className="mt-1.5 ml-1">
                    <summary className="text-xs text-mist cursor-pointer flex items-center gap-1 select-none">
                      <Brain size={12} /> View agent reasoning ({m.reasoning_trace.length} nodes)
                    </summary>
                    <div className="mt-2 space-y-1.5 pl-3 border-l border-line">
                      {m.reasoning_trace.map((step, j) => (
                        <div key={j} className="text-xs">
                          <span className="text-violet font-medium">{step.node}</span>
                          <span className="text-mist"> — {step.detail}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          ))}

          {/* Live reasoning: nodes appear as each one finishes, before any text. */}
          {streaming && liveTrace.length > 0 && (
            <div className="pl-1">
              <div className="space-y-1.5 pl-3 border-l border-mint/30">
                {liveTrace.map((step, j) => (
                  <div key={j} className="text-xs animate-in">
                    <span className="text-violet font-medium">{step.node}</span>
                    <span className="text-mist"> — {step.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {streaming && liveTrace.length === 0 && (
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                {[0, 150, 300].map((d) => (
                  <div
                    key={d}
                    className="w-2 h-2 rounded-full bg-mint animate-bounce"
                    style={{ animationDelay: `${d}ms` }}
                  />
                ))}
              </div>
              <p className="text-xs text-mist">Reading your financial twin…</p>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2 p-4 border-t border-line"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={streaming}
            maxLength={2000}
            placeholder={streaming ? "FinMate is answering…" : "Ask your AI CFO anything…"}
            className="flex-1 bg-white/[0.04] border border-line rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50 disabled:opacity-60"
          />
          {streaming ? (
            <button
              type="button"
              onClick={stop}
              title="Stop generating"
              className="w-10 h-10 rounded-xl border border-line flex items-center justify-center shrink-0 text-fog hover:text-rose hover:border-rose/40 transition-colors"
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="w-10 h-10 rounded-xl bg-gradient-to-br from-mint to-violet flex items-center justify-center shrink-0 disabled:opacity-40 transition-opacity"
            >
              <Send size={16} className="text-onaccent" />
            </button>
          )}
        </form>
      </GlassCard>
    </div>
  );
}
