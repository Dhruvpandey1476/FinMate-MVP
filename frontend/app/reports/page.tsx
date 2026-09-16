"use client";

/**
 * Paid outcomes.
 *
 * Framed as "financial outcomes you can generate" rather than a pricing page,
 * because that is the model: free to understand your money, pay when FinMate
 * produces something worth paying for.
 *
 * Export is the browser's own print-to-PDF against a print stylesheet. A
 * server-side renderer would mean a PDF library and system libraries in the
 * image for output the browser already produces from the same styled view.
 */
import { useEffect, useState } from "react";
import { Lock, Printer, Loader2, Check, ArrowLeft } from "lucide-react";
import { GlassCard, PageHeader } from "@/components/GlassCard";
import { LoadingState, ErrorBoundary } from "@/components/ErrorBoundary";
import { useToast } from "@/components/Toast";
import { api, formatINR } from "@/lib/api";
import type { ReportMeta, GeneratedReport } from "@/lib/types";
import ReportView from "@/components/reports/ReportView";

export default function ReportsPage() {
  const [catalogue, setCatalogue] = useState<ReportMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<GeneratedReport | null>(null);
  const toast = useToast();

  async function load() {
    try {
      setCatalogue(await api.getReports());
    } catch (err) {
      toast.fromError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function unlockAndOpen(report: ReportMeta) {
    setBusy(report.id);
    try {
      if (!report.unlocked) {
        await api.unlockReport(report.id);
        toast.success(`${report.title} unlocked`);
      }
      setOpen(await api.getReport(report.id));
      setCatalogue((c) =>
        c.map((r) => (r.id === report.id ? { ...r, unlocked: true } : r))
      );
    } catch (err) {
      toast.fromError(err);
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <LoadingState label="Loading your outcomes…" />;

  if (open) {
    return (
      <ErrorBoundary>
        <div className="flex items-center justify-between gap-3 mb-5 print:hidden">
          <button
            onClick={() => setOpen(null)}
            className="text-sm text-mist hover:text-white inline-flex items-center gap-1.5"
          >
            <ArrowLeft size={14} /> All outcomes
          </button>
          <button
            onClick={() => window.print()}
            className="text-sm px-4 py-2 rounded-lg bg-gradient-to-br from-mint to-violet text-onaccent font-medium inline-flex items-center gap-2"
          >
            <Printer size={14} /> Save as PDF
          </button>
        </div>
        <ReportView report={open} />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <PageHeader
        title="Financial outcomes"
        subtitle="Understanding your money is free. These are the things FinMate can produce from it."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {catalogue.map((r) => (
          <GlassCard key={r.id} className="flex flex-col">
            <div className="text-2xl mb-2">{r.emoji}</div>
            <p className="text-white font-medium mb-1">{r.title}</p>
            <p className="text-sm text-mist leading-relaxed flex-1">{r.blurb}</p>

            <div className="flex items-center justify-between gap-3 mt-4 pt-3 border-t border-line">
              {r.unlocked ? (
                <span className="text-xs text-mint inline-flex items-center gap-1">
                  <Check size={12} /> Unlocked
                </span>
              ) : (
                <span className="ledger text-sm text-white">₹{r.price_inr}</span>
              )}

              <button
                onClick={() => unlockAndOpen(r)}
                disabled={busy === r.id}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium inline-flex items-center gap-1.5 disabled:opacity-50 ${
                  r.unlocked
                    ? "border border-line text-fog hover:text-white"
                    : "bg-gradient-to-br from-mint to-violet text-onaccent"
                }`}
              >
                {busy === r.id ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : r.unlocked ? null : (
                  <Lock size={11} />
                )}
                {r.unlocked ? "Open" : `Unlock for ₹${r.price_inr}`}
              </button>
            </div>
          </GlassCard>
        ))}
      </div>

      <p className="text-xs text-mist mt-6 max-w-2xl leading-relaxed">
        Demo build: unlocking is instant and nothing is charged. Payments would run
        through Razorpay before the same unlock call — the reports themselves are
        generated from your real data either way.
      </p>
    </ErrorBoundary>
  );
}
