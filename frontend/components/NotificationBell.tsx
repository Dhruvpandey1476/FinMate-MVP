"use client";

/**
 * Proactive nudge inbox.
 *
 * The product only compounds if it reaches out rather than waiting to be
 * opened. This is the in-app channel; the same Notification rows are what a
 * WhatsApp or push integration would deliver.
 */
import { useEffect, useRef, useState } from "react";
import { Bell, AlertTriangle, Info, PartyPopper, RefreshCw } from "lucide-react";
import clsx from "clsx";
import { api, formatDate } from "@/lib/api";
import type { Notification } from "@/lib/types";

const ICONS: Record<string, typeof Bell> = {
  low_balance: AlertTriangle,
  budget_overrun: AlertTriangle,
  goal_risk: AlertTriangle,
  subscription: Info,
  win: PartyPopper,
};

const SEVERITY: Record<string, string> = {
  critical: "text-rose",
  warn: "text-gold",
  info: "text-mint",
};

export default function NotificationBell() {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Quiet failure by design: a broken bell must never block the app.
    api.getNotifications().then(setItems).catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const unread = items.filter((i) => !i.read).length;

  async function refresh() {
    setBusy(true);
    try {
      setItems(await api.refreshNotifications());
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  async function openPanel() {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      try {
        await api.markNotificationsRead();
        setItems((is) => is.map((i) => ({ ...i, read: true })));
      } catch {
        /* ignore */
      }
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={openPanel}
        aria-label={unread > 0 ? `${unread} unread notifications` : "Notifications"}
        className="relative p-2 rounded-lg text-mist hover:text-white transition-colors"
      >
        <Bell size={17} />
        {unread > 0 && (
          <span className="absolute top-1 right-1 min-w-[15px] h-[15px] px-1 rounded-full bg-rose text-ink text-[9px] font-semibold flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-w-[90vw] glass-strong border border-line rounded-xl shadow-glass z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-line">
            <p className="text-sm text-white font-medium">Nudges</p>
            <button
              onClick={refresh}
              disabled={busy}
              aria-label="Refresh nudges"
              className="text-mist hover:text-white transition-colors disabled:opacity-50"
            >
              <RefreshCw size={13} className={busy ? "animate-spin" : ""} />
            </button>
          </div>

          <div className="max-h-96 overflow-y-auto scrollbar-thin">
            {items.length === 0 ? (
              <p className="text-sm text-mist px-4 py-6 text-center">
                Nothing needs your attention right now.
              </p>
            ) : (
              items.map((n) => {
                const Icon = ICONS[n.kind] ?? Info;
                return (
                  <div key={n.id} className="px-4 py-3 border-b border-line last:border-0">
                    <div className="flex items-start gap-2.5">
                      <Icon size={14} className={clsx("mt-0.5 shrink-0", SEVERITY[n.severity])} />
                      <div className="min-w-0">
                        <p className="text-sm text-white leading-snug">{n.title}</p>
                        <p className="text-xs text-mist mt-0.5 leading-relaxed">{n.body}</p>
                        <p className="text-[10px] text-mist mt-1">{formatDate(n.created_at)}</p>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
