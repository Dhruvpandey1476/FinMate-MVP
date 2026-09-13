"use client";

/**
 * Toast notifications.
 *
 * Every page previously did `.catch(() => {})`, so a failing request left the
 * user staring at a spinner with no explanation. Errors now surface here, with
 * quota and rate-limit failures phrased as something the user can act on.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode,
} from "react";
import { AlertTriangle, CheckCircle2, Info, X, Zap } from "lucide-react";
import clsx from "clsx";
import { ApiError } from "@/lib/api";

type ToastKind = "success" | "error" | "info" | "upgrade";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
  detail?: string;
}

interface ToastContextValue {
  push: (kind: ToastKind, message: string, detail?: string) => void;
  success: (message: string, detail?: string) => void;
  error: (message: string, detail?: string) => void;
  info: (message: string, detail?: string) => void;
  /** Turn a thrown error into the right toast automatically. */
  fromError: (err: unknown, fallback?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const ICONS = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
  upgrade: Zap,
};

const STYLES: Record<ToastKind, string> = {
  success: "border-mint/30 text-mint",
  error: "border-rose/30 text-rose",
  info: "border-line text-fog",
  upgrade: "border-gold/30 text-gold",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const push = useCallback((kind: ToastKind, message: string, detail?: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, kind, message, detail }]);
    // Errors linger; successes get out of the way.
    const ttl = kind === "error" || kind === "upgrade" ? 8000 : 4000;
    setTimeout(() => dismiss(id), ttl);
  }, [dismiss]);

  const value = useMemo<ToastContextValue>(() => ({
    push,
    success: (m, d) => push("success", m, d),
    error: (m, d) => push("error", m, d),
    info: (m, d) => push("info", m, d),
    fromError: (err, fallback = "Something went wrong.") => {
      if (err instanceof ApiError) {
        if (err.isQuotaExceeded) {
          push("upgrade", "You've hit your plan limit", err.message);
        } else if (err.isRateLimited) {
          push("info", "Slow down a moment", err.message);
        } else if (err.status === 0) {
          push("error", "Can't reach the server", "Is the backend running?");
        } else {
          push("error", err.message, err.requestId ? `Ref: ${err.requestId}` : undefined);
        }
        return;
      }
      push("error", fallback);
    },
  }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-[calc(100%-2rem)] sm:w-auto">
        {toasts.map((t) => {
          const Icon = ICONS[t.kind];
          return (
            <div
              key={t.id}
              role="status"
              className={clsx(
                "glass-strong rounded-xl border px-4 py-3 shadow-glass flex items-start gap-3 animate-in",
                STYLES[t.kind]
              )}
            >
              <Icon size={16} className="mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white leading-snug">{t.message}</p>
                {t.detail && <p className="text-xs text-mist mt-0.5 leading-snug">{t.detail}</p>}
              </div>
              <button
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
                className="text-mist hover:text-white shrink-0"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return ctx;
}

/**
 * Run an async loader, routing failures to a toast instead of the void.
 * Returns [data, loading, error, reload].
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  options: { quiet?: boolean } = {}
): [T | null, boolean, ApiError | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    loader()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        const apiErr = err instanceof ApiError ? err : new ApiError("Request failed", 0);
        setError(apiErr);
        // 401 already redirects; a quiet loader renders its own inline state.
        if (!options.quiet && apiErr.status !== 401) toast.fromError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return [data, loading, error, () => setNonce((n) => n + 1)];
}
