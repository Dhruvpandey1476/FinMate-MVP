"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Fingerprint, MessageCircleHeart, Target,
  GitBranch, Lightbulb, History, Settings as SettingsIcon, Sparkles, Upload,
} from "lucide-react";
import clsx from "clsx";

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

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex flex-col w-60 shrink-0 h-screen sticky top-0 glass border-r border-line px-4 py-6">
      <div className="flex items-center gap-2 px-2 mb-8">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-mint to-violet flex items-center justify-center shadow-glow">
          <Sparkles size={16} className="text-ink" />
        </div>
        <span className="font-display font-semibold text-lg tracking-tight">FinMate</span>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
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
        })}
      </nav>

      <div className="mt-auto px-3 py-4 rounded-xl glass-strong">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 rounded-full bg-mint animate-pulse" />
          <p className="text-xs text-mint font-medium">AI-Powered</p>
        </div>
        <p className="text-xs text-mist leading-relaxed">
          LangGraph agents, Qdrant vector memory, Neo4j wealth graph.
        </p>
      </div>
    </aside>
  );
}
