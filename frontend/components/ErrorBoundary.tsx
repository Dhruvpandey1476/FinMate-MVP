"use client";

/**
 * Error boundary + shared loading/empty states.
 *
 * A render error anywhere in the tree previously blanked the whole app with no
 * message. This keeps the failure local and offers a way out.
 */
import { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw, Inbox } from "lucide-react";
import { GlassCard } from "./GlassCard";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Wire to Sentry here when it is configured.
    console.error("Render error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    return (
      <GlassCard className="max-w-lg">
        <div className="flex items-start gap-3">
          <AlertTriangle size={18} className="text-rose mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-white font-medium mb-1">This section failed to load</p>
            <p className="text-sm text-mist mb-4">
              {this.state.error.message || "An unexpected error occurred."}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="text-sm px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-2"
            >
              <RefreshCw size={13} /> Try again
            </button>
          </div>
        </div>
      </GlassCard>
    );
  }
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-mist text-sm py-8">
      <div className="flex gap-1">
        {[0, 150, 300].map((delay) => (
          <div
            key={delay}
            className="w-1.5 h-1.5 rounded-full bg-mint animate-bounce"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
      {label}
    </div>
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <GlassCard>
      <div className="shimmer space-y-3">
        <div className="h-3 bg-white/[0.08] rounded-full w-1/3" />
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="h-2.5 bg-white/[0.05] rounded-full" style={{ width: `${90 - i * 15}%` }} />
        ))}
      </div>
    </GlassCard>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <GlassCard className="text-center py-10">
      <Inbox size={26} className="text-mist mx-auto mb-3" />
      <p className="text-white font-medium mb-1">{title}</p>
      <p className="text-sm text-mist max-w-sm mx-auto mb-4">{description}</p>
      {action}
    </GlassCard>
  );
}
