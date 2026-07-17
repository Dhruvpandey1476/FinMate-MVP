"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Fingerprint, MessageCircleHeart, Target,
  GitBranch, Lightbulb, History, Settings as SettingsIcon, Sparkles, Upload, LogOut, Menu, X,
} from "lucide-react";
import clsx from "clsx";
import { clearToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/twin", label: "Financial Twin", icon: Fingerprint },
  { href: "/chat", label: "AI CFO Chat", icon: MessageCircleHeart },
  { href: "/goals", label: "Goals", icon: Target },
  { href: "/simulate", label: "Simulations", icon: GitBranch },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/memory", label: "Memory Timeline", icon: History },
  { href: "/upload", label: "Upload Data", icon: Upload },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-mint to-violet flex items-center justify-center shadow-glow">
        <Sparkles size={16} className="text-ink" />
      </div>
      <span className="font-display font-semibold text-lg tracking-tight">FinMate</span>
    </div>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  const navLinks = (onClick?: () => void) =>
    NAV.map(({ href, label, icon: Icon }) => {
      const active = pathname === href;
      return (
        <Link
          key={href}
          href={href}
          onClick={onClick}
          className={clsx(
            "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors",
            active
              ? "bg-white/[0.06] text-white border border-line"
              : "text-fog hover:text-white hover:bg-white/[0.03]"
          )}
        >
          <Icon size={17} className={active ? "text-mint" : "text-mist"} />
          {label}
        </Link>
      );
    });

  const logoutBtn = (
    <button
      onClick={logout}
      className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-fog hover:text-white hover:bg-white/[0.03] transition-colors"
    >
      <LogOut size={17} className="text-mist" />
      Log out
    </button>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-60 shrink-0 h-screen sticky top-0 glass border-r border-line px-4 py-6">
        <div className="px-2 mb-8">
          <Logo />
        </div>
        <nav className="flex flex-col gap-1">{navLinks()}</nav>
        <div className="mt-auto">{logoutBtn}</div>
        <div className="mt-3 px-3 py-4 rounded-xl glass-strong">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-mint animate-pulse" />
            <p className="text-xs text-mint font-medium">AI-Powered</p>
          </div>
          <p className="text-xs text-mist leading-relaxed">
            LangGraph agents, memory engine, wealth graph.
          </p>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden fixed top-0 inset-x-0 z-40 h-14 flex items-center justify-between px-4 glass border-b border-line">
        <Logo />
        <button onClick={() => setOpen(true)} aria-label="Open menu" className="p-2 text-fog hover:text-white">
          <Menu size={22} />
        </button>
      </header>

      {/* Mobile drawer */}
      {open && (
        <div className="md:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-72 max-w-[80%] glass-strong border-r border-line px-4 py-6 flex flex-col">
            <div className="flex items-center justify-between mb-8 px-2">
              <Logo />
              <button onClick={() => setOpen(false)} aria-label="Close menu" className="p-1 text-fog hover:text-white">
                <X size={22} />
              </button>
            </div>
            <nav className="flex flex-col gap-1">{navLinks(() => setOpen(false))}</nav>
            <div className="mt-auto">{logoutBtn}</div>
          </div>
        </div>
      )}
    </>
  );
}
