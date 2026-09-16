"use client";

/**
 * Quick Add - a WhatsApp-style thread for logging a transaction in one line.
 *
 * Deliberately styled as a WhatsApp conversation because that is the surface we
 * intend to ship on: in India the message thread *is* the product for most
 * people. Nothing here touches Meta's API - it is the same parser a webhook
 * would call, reached through the app. Settings says so plainly rather than
 * letting the demo imply it is live.
 */
import { useEffect, useRef, useState } from "react";
import { MessageCircle, Send, X, Check, Pencil } from "lucide-react";
import { api, formatINR } from "@/lib/api";
import { useToast } from "@/components/Toast";

interface Bubble {
  id: number;
  from: "user" | "finmate";
  text: string;
  /** Set on a confirmation so the reply can offer a one-tap recategorisation. */
  transactionId?: number;
  category?: string;
  learned?: boolean;
}

const EXAMPLES = ["300 auto", "spent 1200 on dinner", "649 netflix"];

let bubbleId = 0;

export default function QuickAdd() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const toast = useToast();

  useEffect(() => {
    if (open && categories.length === 0) {
      api.getQuickAddCategories().then(setCategories).catch(() => {});
    }
  }, [open, categories.length]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles, open]);

  function say(from: Bubble["from"], text: string, extra: Partial<Bubble> = {}) {
    setBubbles((b) => [...b, { id: ++bubbleId, from, text, ...extra }]);
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;

    say("user", message);
    setInput("");
    setBusy(true);
    try {
      const res = await api.quickAdd(message);
      say("finmate", res.reply, {
        transactionId: res.ok ? res.transaction?.id : undefined,
        category: res.transaction?.category,
      });
    } catch (err) {
      toast.fromError(err);
      say("finmate", "That didn't go through. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  async function recategorise(bubble: Bubble, category: string) {
    if (!bubble.transactionId) return;
    setEditing(null);
    try {
      const res = await api.correctCategory(bubble.transactionId, category);
      setBubbles((bs) =>
        bs.map((b) => (b.id === bubble.id ? { ...b, category, learned: true } : b))
      );
      say("finmate", res.reply);
    } catch (err) {
      toast.fromError(err);
    }
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Quick add a transaction"
          className="fixed bottom-5 right-5 z-50 h-14 w-14 rounded-full bg-[rgb(var(--wa-send))] text-[rgb(var(--wa-send-fg))] shadow-lift flex items-center justify-center hover:scale-105 transition-transform"
        >
          <MessageCircle size={24} />
        </button>
      )}

      {open && (
        <div className="fixed bottom-5 right-5 z-50 w-[min(22rem,calc(100vw-2.5rem))] rounded-2xl overflow-hidden shadow-lift border border-line flex flex-col max-h-[min(32rem,calc(100vh-6rem))]">
          {/* WhatsApp-style header */}
          <div className="bg-[rgb(var(--wa-header))] px-4 py-3 flex items-center justify-between shrink-0">
            <div className="min-w-0">
              <p className="text-white text-sm font-medium">FinMate</p>
              <p className="text-white/70 text-[11px]">Quick add · preview</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="text-white/80 hover:text-white shrink-0"
            >
              <X size={18} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2 bg-[rgb(var(--wa-bg))]">
            {bubbles.length === 0 && (
              <div className="text-center py-4">
                <p className="text-[rgb(var(--wa-muted))] text-xs mb-3">
                  Type what you spent — one line is enough.
                </p>
                <div className="flex flex-wrap gap-1.5 justify-center">
                  {EXAMPLES.map((e) => (
                    <button
                      key={e}
                      onClick={() => send(e)}
                      className="text-[11px] px-2.5 py-1 rounded-full border border-[rgb(var(--wa-muted))]/40 text-[rgb(var(--wa-muted))] hover:text-[rgb(var(--wa-text))] transition-colors"
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {bubbles.map((b) => (
              <div key={b.id} className={`flex ${b.from === "user" ? "justify-end" : "justify-start"}`}>
                <div className="max-w-[85%]">
                  <div
                    className={`rounded-lg px-3 py-2 text-[13px] leading-snug ${
                      b.from === "user"
                        ? "bg-[rgb(var(--wa-out))] text-[rgb(var(--wa-text))] rounded-br-sm"
                        : "bg-[rgb(var(--wa-in))] text-[rgb(var(--wa-text))] rounded-bl-sm shadow-sm"
                    }`}
                  >
                    {b.text}
                  </div>

                  {/* One tap to correct, which is what teaches the categoriser. */}
                  {b.transactionId && !b.learned && (
                    <button
                      onClick={() => setEditing(editing === b.id ? null : b.id)}
                      className="text-[11px] text-[rgb(var(--wa-muted))] hover:text-[rgb(var(--wa-text))] mt-1 inline-flex items-center gap-1"
                    >
                      <Pencil size={9} /> Wrong category?
                    </button>
                  )}
                  {b.learned && (
                    <span className="text-[11px] text-[rgb(var(--wa-send))] mt-1 inline-flex items-center gap-1">
                      <Check size={10} /> learned
                    </span>
                  )}

                  {editing === b.id && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {categories.map((c) => (
                        <button
                          key={c}
                          onClick={() => recategorise(b, c)}
                          className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                            c === b.category
                              ? "border-[rgb(var(--wa-send))] text-[rgb(var(--wa-send))]"
                              : "border-[rgb(var(--wa-muted))]/40 text-[rgb(var(--wa-muted))] hover:text-[rgb(var(--wa-text))]"
                          }`}
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {busy && (
              <div className="flex justify-start">
                <div className="bg-[rgb(var(--wa-in))] rounded-lg rounded-bl-sm px-3 py-2.5 flex gap-1">
                  {[0, 150, 300].map((d) => (
                    <span
                      key={d}
                      className="w-1.5 h-1.5 rounded-full bg-[rgb(var(--wa-muted))] animate-bounce"
                      style={{ animationDelay: `${d}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-center gap-2 p-2 bg-[rgb(var(--wa-input))] border-t border-[rgb(var(--wa-muted))]/20 shrink-0"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={280}
              placeholder="e.g. 300 auto"
              className="flex-1 min-w-0 bg-[rgb(var(--wa-field))] rounded-full px-3.5 py-2 text-[13px] text-[rgb(var(--wa-text))] placeholder:text-[rgb(var(--wa-muted))] outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || busy}
              aria-label="Send"
              className="h-9 w-9 rounded-full bg-[rgb(var(--wa-send))] flex items-center justify-center shrink-0 disabled:opacity-40"
            >
              <Send size={15} className="text-[rgb(var(--wa-send-fg))]" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
