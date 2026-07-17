"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { api, setToken } from "@/lib/api";

type Mode = "magic" | "password" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("magic");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [devLink, setDevLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);

  // If the URL carries a magic token, verify it and log in.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const magic = params.get("magic");
    if (!magic) return;
    setVerifying(true);
    api
      .magicVerify(magic)
      .then((res) => {
        setToken(res.token);
        router.replace("/");
      })
      .catch((e) => {
        setError(e.message || "This login link is invalid or expired.");
        setVerifying(false);
      });
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");
    setDevLink("");
    setLoading(true);
    try {
      if (mode === "magic") {
        const res = await api.magicRequest(email, name);
        if (res.sent) setNotice(`Check your inbox — we sent a login link to ${res.email}.`);
        else {
          setNotice("Email isn't configured yet (dev mode). Use this one-time link:");
          setDevLink(res.dev_link);
        }
      } else {
        const res =
          mode === "signup"
            ? await api.signup(name, email, password)
            : await api.login(email, password);
        setToken(res.token);
        router.push("/");
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function useDemo() {
    setMode("password");
    setEmail("demo@finmate.ai");
    setPassword("demo1234");
  }

  if (verifying) {
    return <div className="min-h-screen flex items-center justify-center text-mist">Logging you in…</div>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-2 justify-center mb-8">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-mint to-violet flex items-center justify-center shadow-glow">
            <Sparkles size={18} className="text-ink" />
          </div>
          <span className="font-display font-semibold text-2xl tracking-tight">FinMate</span>
        </div>

        <div className="glass-strong rounded-2xl border border-line p-7">
          <h1 className="text-xl font-semibold mb-1">
            {mode === "signup" ? "Create your account" : mode === "magic" ? "Log in or sign up" : "Log in with password"}
          </h1>
          <p className="text-sm text-mist mb-6">
            {mode === "magic"
              ? "Enter your email — we'll send you a one-tap login link. No password needed."
              : mode === "signup"
              ? "Start building your memory-powered Financial Twin."
              : "For accounts with a password (like the demo)."}
          </p>

          <form onSubmit={submit} className="space-y-4">
            {(mode === "signup" || mode === "magic") && (
              <Field label={mode === "magic" ? "Name (optional)" : "Name"} value={name} onChange={setName} placeholder="Your name" />
            )}
            <Field label="Email" type="email" value={email} onChange={setEmail} placeholder="you@email.com" />
            {mode !== "magic" && (
              <Field label="Password" type="password" value={password} onChange={setPassword} placeholder="••••••••" />
            )}

            {error && <p className="text-sm text-rose">{error}</p>}
            {notice && <p className="text-sm text-mint">{notice}</p>}
            {devLink && (
              <a href={devLink} className="block text-sm text-violet break-all underline">
                {devLink}
              </a>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-mint to-violet text-ink font-medium text-sm disabled:opacity-60"
            >
              {loading ? "Please wait…" : mode === "magic" ? "Send login link" : mode === "signup" ? "Sign up" : "Log in"}
            </button>
          </form>

          <div className="mt-5 space-y-2 text-sm">
            {mode !== "magic" && (
              <button onClick={() => setMode("magic")} className="block text-mist hover:text-white">
                ← Use a magic email link instead
              </button>
            )}
            {mode === "magic" && (
              <button onClick={() => setMode("password")} className="block text-mist hover:text-white">
                Log in with a password
              </button>
            )}
            <button onClick={useDemo} className="block text-mint hover:underline">
              Try the demo account
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, type = "text", placeholder,
}: {
  label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs text-fog">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full px-3 py-2.5 rounded-xl bg-white/[0.04] border border-line text-sm text-white placeholder:text-mist focus:outline-none focus:border-mint/50"
      />
    </label>
  );
}
