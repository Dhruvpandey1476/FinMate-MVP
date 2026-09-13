import clsx from "clsx";
import { ReactNode } from "react";

export function GlassCard({
  children,
  className,
  strong = false,
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  strong?: boolean;
  /** Lift on hover. Use only where the card is actually interactive. */
  hover?: boolean;
}) {
  return (
    <div
      className={clsx(
        "rounded-2xl shadow-glass p-5",
        strong ? "glass-strong" : "glass",
        hover && "card-hover cursor-pointer",
        className
      )}
    >
      {children}
    </div>
  );
}

export function StatRow({
  label,
  value,
  accent = "text-white",
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-line last:border-0">
      <span className="text-sm text-fog min-w-0 truncate">{label}</span>
      <span className={clsx("ledger text-sm font-medium shrink-0", accent)}>{value}</span>
    </div>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="font-display text-2xl font-semibold tracking-tight text-white text-balance">
        {title}
      </h1>
      {subtitle && <p className="text-sm text-mist mt-1 max-w-2xl leading-relaxed">{subtitle}</p>}
    </div>
  );
}
