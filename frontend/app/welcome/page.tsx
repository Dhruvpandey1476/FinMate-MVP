"use client";

import Link from "next/link";
import { useState } from "react";
import { Sparkles, Brain, LineChart, Target, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

export default function Welcome() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function join(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    try {
      const r = await api.joinWaitlist(email);
      setMsg(r.message || "You're on the list!");
      setEmail("");
    } catch (err: any) {
      setMsg(err.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      {/* Nav */}
      <header className="flex items-center justify-between px-6 md:px-12 py-6 max-w-6xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-mint to-violet flex items-center justify-center shadow-glow">
            <Sparkles size={16} className="text-ink" />
          </div>
          <span className="font-display font-semibold text-lg tracking-tight">FinMate</span>
        </div>
        <Link href="/login" className="text-sm text-mist hover:text-white">
          Log in
        </Link>
      </header>

      {/* Hero */}
      <section className="max-w-3xl mx-auto text-center px-6 pt-16 pb-20">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-line text-xs text-mint mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-mint animate-pulse" />
          Memory-powered financial AI
        </div>
        <h1 className="font-display text-4xl md:text-6xl font-semibold tracking-tight leading-[1.05]">
          Your money, with a
          <span className="bg-gradient-to-r from-mint to-violet bg-clip-text text-transparent"> memory</span>.
        </h1>
        <p className="text-mist text-lg mt-6 max-w-xl mx-auto">
          Budgeting apps show you the past. FinMate builds a financial digital twin that
          remembers your history, simulates your future, and acts as your AI CFO — telling
          you what to actually do.
        </p>
        <div className="flex items-center justify-center gap-3 mt-9">
          <Link
            href="/login"
            className="px-6 py-3 rounded-xl bg-gradient-to-r from-mint to-violet text-ink font-medium text-sm"
          >
            Get started free
          </Link>
          <Link
            href="/login"
            className="px-6 py-3 rounded-xl border border-line text-sm text-white hover:bg-white/[0.04]"
          >
            Try the demo
          </Link>
        </div>
        <p className="text-xs text-mist mt-4">No credit card. Free while in beta.</p>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-6 pb-24 grid grid-cols-1 md:grid-cols-2 gap-5">
        <Feature icon={<Brain size={18} />} title="It remembers you"
          desc="A three-tier memory engine learns your preferences, patterns, and plans from every chat and statement — so each session is smarter than the last." />
        <Feature icon={<LineChart size={18} />} title="It simulates your future"
          desc="Run real what-if projections: a big purchase, a raise, a new SIP. See the impact on your net worth before you commit." />
        <Feature icon={<Target size={18} />} title="Goal-aware advice"
          desc="Every recommendation is weighed against your actual goals and priorities — not generic tips." />
        <Feature icon={<ShieldCheck size={18} />} title="Transparent reasoning"
          desc="The AI CFO shows its work: which financial data, memories, and goals shaped every answer." />
      </section>

      {/* Waitlist */}
      <section className="max-w-xl mx-auto px-6 pb-24 text-center">
        <div className="glass-strong rounded-2xl border border-line p-8">
          <h2 className="text-xl font-semibold mb-2">Not ready to sign up? Join the waitlist.</h2>
          <p className="text-sm text-mist mb-6">
            Drop your email and we'll let you know as new features ship.
          </p>
          <form onSubmit={join} className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@email.com"
              className="flex-1 px-4 py-3 rounded-xl bg-white/[0.04] border border-line text-sm text-white placeholder:text-mist focus:outline-none focus:border-mint/50"
            />
            <button
              type="submit"
              disabled={busy}
              className="px-6 py-3 rounded-xl bg-gradient-to-r from-mint to-violet text-ink font-medium text-sm disabled:opacity-60"
            >
              {busy ? "…" : "Join waitlist"}
            </button>
          </form>
          {msg && <p className="text-sm text-mint mt-4">{msg}</p>}
        </div>
      </section>

      <footer className="text-center text-xs text-mist pb-10">
        © FinMate. Built for people who want their finances to think ahead.
      </footer>
    </div>
  );
}

function Feature({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="glass rounded-2xl border border-line p-6">
      <div className="w-9 h-9 rounded-lg bg-white/[0.05] flex items-center justify-center text-mint mb-4">
        {icon}
      </div>
      <h3 className="font-medium text-white mb-1.5">{title}</h3>
      <p className="text-sm text-mist leading-relaxed">{desc}</p>
    </div>
  );
}
