import clsx from "clsx";
import { ReactNode } from "react";

export function GlassCard({
  children,
  className,
  strong = false,
}: {
  children: ReactNode;
  className?: string;
  strong?: boolean;
}) {
  return (
    <div
      className={clsx(
        "rounded-2xl shadow-glass p-5",
        strong ? "glass-strong" : "glass",
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
    <div className="flex items-center justify-between py-2 border-b border-line last:border-0">
      <span className="text-sm text-fog">{label}</span>
      <span className={clsx("ledger text-sm font-medium", accent)}>{value}</span>
    </div>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="font-display text-2xl font-semibold tracking-tight text-white">{title}</h1>
      {subtitle && <p className="text-sm text-mist mt-1">{subtitle}</p>}
    </div>
  );
}
