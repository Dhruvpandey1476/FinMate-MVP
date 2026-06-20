"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Brain, Zap } from "lucide-react";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { api } from "@/lib/api";

const SUGGESTIONS = [
  "Can I afford a ₹50,000 laptop?",
  "Why am I overspending?",
  "How can I save more?",
  "What should I prioritize?",
  "How close am I to financial freedom?",
  "What if I invest ₹10,000/month?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getChatHistory().then(setMessages).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.sendChat(text);
      setMessages((m) => [...m, { role: "assistant", content: res.reply, reasoning_trace: res.reasoning_trace }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "Something went wrong reaching the AI CFO agent. Please check that the backend is running." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      <div className="flex items-center justify-between mb-4">
        <PageHeader title="AI CFO Chat" subtitle="Ask anything about your money — powered by LangGraph agents." />
        <div className="flex items-center gap-1.5 text-xs text-mint bg-mint/10 px-3 py-1.5 rounded-full border border-mint/20">
          <Zap size={12} />
          AI-Powered
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
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] ${m.role === "user" ? "" : "w-full"}`}>
                <div
                  className={`rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                    m.role === "user" ? "bg-gradient-to-br from-mint/20 to-violet/20 border border-mint/20 text-white" : "glass text-white"
                  }`}
                >
                  {m.content}
                </div>
                {m.reasoning_trace && (
                  <details className="mt-1.5 ml-1">
                    <summary className="text-xs text-mist cursor-pointer flex items-center gap-1 select-none">
                      <Brain size={12} /> View agent reasoning ({m.reasoning_trace.length} nodes)
                    </summary>
                    <div className="mt-2 space-y-1.5 pl-3 border-l border-line">
                      {m.reasoning_trace.map((step: any, j: number) => (
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
          {loading && (
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <div className="w-2 h-2 rounded-full bg-mint animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 rounded-full bg-mint animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 rounded-full bg-mint animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
              <p className="text-xs text-mist">FinMate AI is analyzing your financial twin…</p>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); send(input); }}
          className="flex items-center gap-2 p-4 border-t border-line"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask your AI CFO anything…"
            className="flex-1 bg-white/[0.04] border border-line rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-mist outline-none focus:border-mint/50"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-10 h-10 rounded-xl bg-gradient-to-br from-mint to-violet flex items-center justify-center shrink-0 disabled:opacity-50"
          >
            <Send size={16} className="text-ink" />
          </button>
        </form>
      </GlassCard>
    </div>
  );
}
